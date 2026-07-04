"""shop_manager.py — จัดการการโหลด/บันทึก/ตรวจสอบไฟล์ร้านค้า (JSON)

แต่ละร้านค้า = ไฟล์ .json 1 ไฟล์ ในโฟลเดอร์ plugins/bgshop/shops/
โมดูลนี้ไม่ยุ่งกับระบบเงิน (นั่นเป็นหน้าที่ของ EconomyCore) ทำเฉพาะข้อมูลร้าน
"""

from __future__ import annotations

import json
import os
import re
from typing import Any


# ค่าที่ยอมรับสำหรับ field "currency" ของแต่ละไอเทม
VALID_CURRENCIES = ("money", "point")

# field ที่ไอเทมทุกชิ้น "ต้องมี" มิฉะนั้นจะถูกข้ามพร้อม log เตือน
REQUIRED_ITEM_FIELDS = ("item_id", "amount", "price", "currency")


def normalize_currency(value: Any) -> str | None:
    """แปลงค่า currency ที่ผู้ใช้พิมพ์ให้เป็นมาตรฐาน (money / point)

    รองรับคำพ้อง เช่น points, pt, coin ฯลฯ คืน None ถ้าไม่รู้จัก
    """
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in ("money", "cash", "coin", "coins", "$", "เงิน"):
        return "money"
    if text in ("point", "points", "pt", "pts", "พอยต์", "แต้ม"):
        return "point"
    return None


class Shop:
    """ตัวแทนของร้านค้าหนึ่งร้าน (map ตรงกับไฟล์ JSON หนึ่งไฟล์)"""

    def __init__(self, file_id: str, path: str, data: dict):
        # file_id = ชื่อไฟล์ไม่รวม .json ใช้เป็น "ชื่อร้าน" ในคำสั่งต่าง ๆ
        self.file_id: str = file_id
        self.path: str = path
        self.shop_name: str = str(data.get("shop_name") or file_id)
        self.icon: str = str(data.get("icon") or "")
        self.enabled: bool = bool(data.get("enabled", True))
        # permission: ถ้าเป็น "" / None → ร้าน public (ทุกคนเข้าได้)
        perm = data.get("permission")
        self.permission: str | None = perm if (perm and str(perm).strip()) else None
        # เก็บ items ตามที่ตรวจสอบแล้วเท่านั้น
        self.items: list[dict] = []

    @property
    def is_public(self) -> bool:
        """ร้าน public = ไม่ตั้ง permission → ทุกคนเข้าได้"""
        return self.permission is None

    def to_dict(self) -> dict:
        """แปลงกลับเป็น dict เพื่อบันทึกลงไฟล์ JSON"""
        return {
            "shop_name": self.shop_name,
            "icon": self.icon,
            "enabled": self.enabled,
            "permission": self.permission if self.permission else "",
            "items": self.items,
        }


class ShopManager:
    """โหลด/บันทึก/สร้าง/ลบ ร้านค้าทั้งหมดจากโฟลเดอร์ shops/"""

    def __init__(self, data_folder: str, logger):
        self.logger = logger
        # โฟลเดอร์ plugins/bgshop/shops/
        self.shops_dir = os.path.join(data_folder, "shops")
        # เก็บร้านที่โหลดสำเร็จ: file_id -> Shop
        self.shops: dict[str, Shop] = {}

    # ------------------------------------------------------------------ #
    #  การโหลด
    # ------------------------------------------------------------------ #
    def ensure_dirs(self) -> None:
        """สร้างโฟลเดอร์ shops/ ถ้ายังไม่มี"""
        os.makedirs(self.shops_dir, exist_ok=True)

    def load_all(self) -> None:
        """โหลดไฟล์ .json ทุกไฟล์ในโฟลเดอร์ shops/ ใหม่ทั้งหมด

        - ถ้าโฟลเดอร์ว่าง → สร้างร้านตัวอย่าง general.json ให้อัตโนมัติ
        - ถ้าไฟล์ JSON พัง → log ชื่อไฟล์ แล้วข้าม (ไม่ทำให้ปลั๊กอินล่ม)
        """
        self.ensure_dirs()
        self.shops.clear()

        json_files = [
            f for f in sorted(os.listdir(self.shops_dir))
            if f.lower().endswith(".json")
        ]

        # โฟลเดอร์ว่าง → สร้างร้านตัวอย่าง
        if not json_files:
            self.logger.info("ไม่พบไฟล์ร้านค้า กำลังสร้างร้านตัวอย่าง general.json ...")
            self._create_sample_shop()
            json_files = ["general.json"]

        for filename in json_files:
            file_id = filename[:-5]  # ตัด ".json" ออก
            path = os.path.join(self.shops_dir, filename)
            shop = self._load_one(file_id, path)
            if shop is not None:
                self.shops[file_id] = shop

        self.logger.info(f"โหลดร้านค้าสำเร็จ {len(self.shops)} ร้าน")

    def _load_one(self, file_id: str, path: str) -> Shop | None:
        """โหลดร้านเดียว คืน None ถ้าไฟล์พังจน parse ไม่ได้"""
        try:
            with open(path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except json.JSONDecodeError as exc:
            # JSON พัง — แจ้งชื่อไฟล์แล้วข้าม
            self.logger.error(f"ไฟล์ร้านค้า '{path}' เป็น JSON ที่ไม่ถูกต้อง: {exc} — ข้ามไฟล์นี้")
            return None
        except OSError as exc:
            self.logger.error(f"อ่านไฟล์ร้านค้า '{path}' ไม่ได้: {exc} — ข้ามไฟล์นี้")
            return None

        if not isinstance(data, dict):
            self.logger.error(f"ไฟล์ร้านค้า '{path}' ต้องเป็น object (dict) — ข้ามไฟล์นี้")
            return None

        shop = Shop(file_id, path, data)

        # ตรวจสอบไอเทมทีละชิ้น — ชิ้นที่ field ไม่ครบให้ข้ามพร้อม log
        raw_items = data.get("items", [])
        if not isinstance(raw_items, list):
            self.logger.warning(f"ร้าน '{file_id}' field 'items' ไม่ใช่ list — ถือว่าไม่มีไอเทม")
            raw_items = []

        for index, raw in enumerate(raw_items):
            cleaned = self._validate_item(file_id, index, raw)
            if cleaned is not None:
                shop.items.append(cleaned)

        return shop

    def _validate_item(self, file_id: str, index: int, raw: Any) -> dict | None:
        """ตรวจสอบไอเทมหนึ่งชิ้น คืน dict ที่ทำความสะอาดแล้ว หรือ None ถ้าไม่ผ่าน"""
        if not isinstance(raw, dict):
            self.logger.warning(f"ร้าน '{file_id}' ไอเทมลำดับ {index} ไม่ใช่ object — ข้าม")
            return None

        # เช็ค field ที่จำเป็นครบไหม
        missing = [f for f in REQUIRED_ITEM_FIELDS if f not in raw or raw.get(f) in (None, "")]
        if missing:
            self.logger.warning(
                f"ร้าน '{file_id}' ไอเทมลำดับ {index} ขาด field ที่จำเป็น: {missing} — ข้าม"
            )
            return None

        # ตรวจ currency
        currency = normalize_currency(raw.get("currency"))
        if currency is None:
            self.logger.warning(
                f"ร้าน '{file_id}' ไอเทมลำดับ {index} currency ไม่ถูกต้อง "
                f"(ต้องเป็น money หรือ point) — ข้าม"
            )
            return None

        # ตรวจ amount / price ให้เป็นจำนวนเต็มบวก
        try:
            amount = int(raw.get("amount"))
            price = int(raw.get("price"))
        except (TypeError, ValueError):
            self.logger.warning(
                f"ร้าน '{file_id}' ไอเทมลำดับ {index} amount/price ไม่ใช่ตัวเลข — ข้าม"
            )
            return None

        if amount <= 0 or price < 0:
            self.logger.warning(
                f"ร้าน '{file_id}' ไอเทมลำดับ {index} amount ต้องมากกว่า 0 และ price ต้องไม่ติดลบ — ข้าม"
            )
            return None

        item_id = str(raw.get("item_id")).strip()

        # สร้าง dict ที่สะอาด (เก็บ field เสริมอย่าง name/icon/description ไว้ด้วย)
        return {
            "name": str(raw.get("name") or item_id),
            "item_id": item_id,
            "amount": amount,
            "price": price,
            "currency": currency,
            "icon": str(raw.get("icon") or ""),
            "description": str(raw.get("description") or ""),
        }

    # ------------------------------------------------------------------ #
    #  การบันทึก / สร้าง / ลบ
    # ------------------------------------------------------------------ #
    def save(self, shop: Shop) -> bool:
        """บันทึกร้านลงไฟล์ JSON (ensure_ascii=False, indent=2)"""
        try:
            self.ensure_dirs()
            with open(shop.path, "w", encoding="utf-8") as fp:
                json.dump(shop.to_dict(), fp, ensure_ascii=False, indent=2)
            return True
        except OSError as exc:
            self.logger.error(f"บันทึกร้าน '{shop.file_id}' ไม่สำเร็จ: {exc}")
            return False

    @staticmethod
    def is_valid_file_id(file_id: str) -> bool:
        """ชื่อไฟล์ร้านต้องปลอดภัย (กัน path traversal) — a-z A-Z 0-9 _ - เท่านั้น"""
        return bool(re.fullmatch(r"[A-Za-z0-9_\-]+", file_id or ""))

    def create_shop(self, file_id: str, display_name: str) -> Shop | None:
        """สร้างร้านใหม่ (ไฟล์ JSON เปล่า) คืน Shop หรือ None ถ้าซ้ำ/ชื่อผิด"""
        if not self.is_valid_file_id(file_id):
            return None
        if file_id in self.shops:
            return None  # มีอยู่แล้ว

        path = os.path.join(self.shops_dir, f"{file_id}.json")
        if os.path.exists(path):
            return None

        shop = Shop(
            file_id,
            path,
            {
                "shop_name": display_name or file_id,
                "icon": "textures/items/emerald",
                "enabled": True,
                "permission": "",  # public โดยค่าเริ่มต้น
                "items": [],
            },
        )
        if not self.save(shop):
            return None
        self.shops[file_id] = shop
        return shop

    def delete_shop(self, file_id: str) -> bool:
        """ลบร้าน (ลบไฟล์ JSON ออกจากดิสก์ด้วย)"""
        shop = self.shops.get(file_id)
        if shop is None:
            return False
        try:
            if os.path.exists(shop.path):
                os.remove(shop.path)
        except OSError as exc:
            self.logger.error(f"ลบไฟล์ร้าน '{file_id}' ไม่สำเร็จ: {exc}")
            return False
        self.shops.pop(file_id, None)
        return True

    def get(self, file_id: str) -> Shop | None:
        """หาร้านจาก file_id ตรง ๆ ก่อน ถ้าไม่เจอลองเทียบกับ shop_name (display)"""
        shop = self.shops.get(file_id)
        if shop is not None:
            return shop
        for candidate in self.shops.values():
            if candidate.shop_name == file_id:
                return candidate
        return None

    def _create_sample_shop(self) -> None:
        """สร้างร้านตัวอย่าง general.json ตอนโฟลเดอร์ว่าง"""
        sample = {
            "shop_name": "ร้านค้าทั่วไป",
            "icon": "textures/items/emerald",
            "enabled": True,
            "permission": "",
            "items": [
                {
                    "name": "§aเพชร x8",
                    "item_id": "minecraft:diamond",
                    "amount": 8,
                    "price": 500,
                    "currency": "money",
                    "icon": "textures/items/diamond",
                    "description": "เพชรคุณภาพดี",
                },
                {
                    "name": "§bธาตุเนเธอไรต์",
                    "item_id": "minecraft:netherite_ingot",
                    "amount": 1,
                    "price": 10,
                    "currency": "point",
                    "icon": "textures/items/netherite_ingot",
                    "description": "ซื้อด้วยพอยต์เท่านั้น",
                },
            ],
        }
        path = os.path.join(self.shops_dir, "general.json")
        try:
            with open(path, "w", encoding="utf-8") as fp:
                json.dump(sample, fp, ensure_ascii=False, indent=2)
        except OSError as exc:
            self.logger.error(f"สร้างร้านตัวอย่างไม่สำเร็จ: {exc}")
