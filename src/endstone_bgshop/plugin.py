"""plugin.py — โค้ดหลักของปลั๊กอิน BGSHOP

- เชื่อมต่อ EconomyCore ผ่าน Service Manager (ห้ามเขียนระบบเงินเอง)
- รองรับหลายร้านค้า, หักเงิน/พอยต์รายไอเทม, permission รายร้าน
- UI ด้วย ActionForm / MessageForm ภาษาไทย
"""

from __future__ import annotations

from endstone.plugin import Plugin
from endstone.form import ActionForm, MessageForm
from endstone.inventory import ItemStack
from endstone.permissions import Permission, PermissionDefault
from endstone import Player


# สีโค้ด § ที่ใช้บ่อย (เพื่ออ่านง่าย)
C_GREEN = "§a"
C_AQUA = "§b"
C_YELLOW = "§e"
C_RED = "§c"
C_GOLD = "§6"
C_GRAY = "§7"
C_WHITE = "§f"
C_RESET = "§r"


class BGShop(Plugin):
    # ---- metadata ของปลั๊กอิน (มาตรฐาน Endstone 0.11.x) ----
    api_version = "0.11"
    # ต้องพึ่ง economy_core เพื่อให้โหลดก่อนเสมอ
    depend = ["economy_core"]

    # ---- ประกาศคำสั่ง (commands) ----
    commands = {
        "shop": {
            "description": "เปิดหน้าร้านค้า BGSHOP",
            "usages": ["/shop"],
            "permissions": ["bgshop.use"],
        },
        "bgshop": {
            "description": "คำสั่งจัดการร้านค้า BGSHOP (สำหรับ OP)",
            # ใช้ message เพื่อรับ argument แบบยืดหยุ่น แล้ว parse เองภายใน
            "usages": ["/bgshop [args: message]"],
            "permissions": ["bgshop.admin"],
        },
    }

    # ---- ประกาศ permission พื้นฐาน ----
    permissions = {
        "bgshop.use": {
            "description": "อนุญาตให้ใช้ /shop เปิดหน้าร้าน",
            "default": True,  # ทุกคนใช้ได้
        },
        "bgshop.admin": {
            "description": "อนุญาตให้จัดการร้านค้า และเข้าได้ทุกร้าน (bypass)",
            "default": "op",  # เฉพาะ OP
        },
    }

    def __init__(self):
        super().__init__()
        self.economy = None
        self.shop_manager = None
        # เก็บชื่อ permission ของร้านที่ลงทะเบียนแล้ว กันลงซ้ำ
        self._registered_perms: set[str] = set()

    # ================================================================== #
    #  วงจรชีวิตของปลั๊กอิน
    # ================================================================== #
    def on_enable(self) -> None:
        # --- 1) เชื่อมต่อ EconomyCore ---
        self.economy = self._resolve_economy()
        if self.economy is None:
            self.logger.error("ไม่พบ EconomyCore! ปิดการทำงาน BGSHOP")
            self.server.plugin_manager.disable_plugin(self)
            return

        # ตรวจว่ามีเมธอดฝั่งเงินครบไหม (ฝั่งเงินถือเป็นข้อบังคับ)
        for method in ("has_money", "remove_money", "add_money"):
            if not hasattr(self.economy, method):
                self.logger.error(
                    f"EconomyCore ไม่มีเมธอด '{method}' — ปิดการทำงาน BGSHOP"
                )
                self.server.plugin_manager.disable_plugin(self)
                return

        # --- 2) โหลดร้านค้าทั้งหมด ---
        # import แบบ relative ภายในเมธอดเพื่อให้แน่ใจว่า data_folder พร้อมแล้ว
        from endstone_bgshop.shop_manager import ShopManager

        self.shop_manager = ShopManager(str(self.data_folder), self.logger)
        self._reload_shops()

        self.logger.info(f"{C_GREEN}BGSHOP เปิดใช้งานเรียบร้อย!")

    def on_disable(self) -> None:
        self.logger.info("BGSHOP ปิดการทำงานแล้ว")

    def _resolve_economy(self):
        """ดึง API ของ EconomyCore — วิธีที่ 1 ผ่าน Service Manager, วิธีที่ 2 ผ่าน Plugin Manager"""
        economy = None
        # วิธีที่ 1: ผ่าน Service Manager (ใช้เป็นหลัก)
        try:
            economy = self.server.service_manager.load("EconomyCore")
        except Exception as exc:  # noqa: BLE001 - กัน service manager โยน error
            self.logger.warning(f"โหลด EconomyCore ผ่าน Service Manager ไม่ได้: {exc}")
            economy = None

        # วิธีที่ 2 (fallback): ผ่าน Plugin Manager
        if economy is None:
            plugin = self.server.plugin_manager.get_plugin("economy_core")
            economy = getattr(plugin, "api", None) if plugin else None

        return economy

    # ================================================================== #
    #  การโหลดร้าน + ลงทะเบียน permission
    # ================================================================== #
    def _reload_shops(self) -> None:
        """โหลดไฟล์ JSON ทุกร้านใหม่ แล้วลงทะเบียน permission รายร้าน"""
        self.shop_manager.load_all()
        for shop in self.shop_manager.shops.values():
            if shop.permission:
                self._ensure_permission(shop.permission, public=False)

    def _ensure_permission(self, name: str, public: bool) -> None:
        """ลงทะเบียน permission ของร้านแบบ dynamic ถ้ายังไม่มีอยู่

        ตั้ง default = FALSE สำหรับร้านที่ต้องมีสิทธิ์ (public ไม่ต้องลงทะเบียน)
        Endstone 0.11.4 ไม่มี public API สำหรับ add_permission ตรง ๆ จึง
        พยายามเรียกเมธอดที่อาจมี และถ้าไม่มีจริง ๆ ก็ทำงานต่อได้
        (การบังคับสิทธิ์อาศัย player.has_permission ซึ่งทำงานได้อยู่แล้ว)
        """
        if not name or name in self._registered_perms:
            return

        pm = self.server.plugin_manager
        try:
            # ถ้ามี permission นี้อยู่แล้วก็ไม่ต้องทำอะไร
            existing = None
            try:
                existing = pm.get_permission(name)
            except Exception:  # noqa: BLE001
                existing = None
            if existing is not None:
                self._registered_perms.add(name)
                return

            default = PermissionDefault.TRUE if public else PermissionDefault.FALSE
            perm = Permission(name, f"BGSHOP: สิทธิ์เข้าร้านค้า {name}", default)

            added = False
            for method_name in ("add_permission", "register_permission"):
                fn = getattr(pm, method_name, None)
                if callable(fn):
                    fn(perm)
                    added = True
                    break

            if added:
                try:
                    pm.recalculate_permission_defaults(perm)
                except Exception:  # noqa: BLE001
                    pass
                self.logger.info(f"ลงทะเบียน permission ร้านค้า: {name} (default={default.name})")
            else:
                # ไม่มี API ให้ลงทะเบียน — enforcement ยังทำงานผ่าน has_permission
                self.logger.info(
                    f"ประกาศ permission ร้านค้า '{name}' (ตรวจสอบผ่าน has_permission); "
                    f"มอบสิทธิ์ให้ผู้เล่นผ่านปลั๊กอิน permission ภายนอก"
                )
            self._registered_perms.add(name)
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(f"ลงทะเบียน permission '{name}' ไม่สำเร็จ: {exc}")

    # ================================================================== #
    #  ตัวช่วยเรื่องสิทธิ์ + เศรษฐกิจ
    # ================================================================== #
    def _is_admin(self, player: Player) -> bool:
        """OP ที่มี bgshop.admin เข้าได้ทุกร้าน (bypass)"""
        return player.has_permission("bgshop.admin") or player.is_op

    def _can_access(self, player: Player, shop) -> bool:
        """ตรวจว่าผู้เล่นมีสิทธิ์เข้าร้านนี้ไหม"""
        if not shop.enabled:
            return False
        if self._is_admin(player):
            return True
        if shop.is_public:
            return True
        return player.has_permission(shop.permission)

    def _currency_supported(self, currency: str) -> bool:
        """ตรวจว่า EconomyCore รองรับสกุลเงินที่ระบุไหม (พอยต์อาจไม่มีใน API)"""
        if currency == "money":
            return hasattr(self.economy, "has_money") and hasattr(self.economy, "remove_money")
        if currency == "point":
            return hasattr(self.economy, "has_points") and hasattr(self.economy, "remove_points")
        return False

    def _get_balance(self, player: Player, currency: str):
        """พยายามอ่านยอดคงเหลือ (ถ้า API มีเมธอด) — คืน None ถ้าอ่านไม่ได้"""
        candidates = (
            ("get_money", "get_balance", "balance", "money")
            if currency == "money"
            else ("get_points", "points", "get_point")
        )
        for name in candidates:
            fn = getattr(self.economy, name, None)
            if callable(fn):
                try:
                    return fn(player)
                except Exception:  # noqa: BLE001
                    continue
        return None

    # ================================================================== #
    #  ตัวช่วยหา Player จาก sender (รองรับ NPC / CommandSenderWrapper)
    # ================================================================== #
    def _resolve_player(self, sender) -> Player | None:
        """พยายามดึง Player จาก sender ไม่ว่าจะเป็นชนิดใด

        1. sender เป็น Player อยู่แล้ว → ใช้เลย
        2. sender เป็น wrapper → ลองดึงชื่อแล้วหาผู้เล่นจาก server.get_player()
        3. หาไม่เจอ → คืน None
        """
        if isinstance(sender, Player):
            return sender

        # sender อาจเป็น CommandSenderWrapper หรือ NPC entity
        # ลองหาผู้เล่นจากชื่อของ sender
        try:
            name = sender.name
            if name:
                player = self.server.get_player(name)
                if player is not None:
                    return player
        except Exception:  # noqa: BLE001
            pass

        # fallback: ถ้ามี attribute ที่ชี้ไปหา player ตัวจริง
        for attr in ("player", "sender", "_sender", "source"):
            inner = getattr(sender, attr, None)
            if isinstance(inner, Player):
                return inner

        return None

    # ================================================================== #
    #  การจัดการคำสั่ง
    # ================================================================== #
    def on_command(self, sender, command, args) -> bool:
        name = command.name.lower()

        if name == "shop":
            # พยายามหา Player จาก sender (รองรับ NPC / wrapper)
            player = self._resolve_player(sender)
            if player is None:
                sender.send_error_message("คำสั่งนี้ใช้ได้เฉพาะผู้เล่นในเกมเท่านั้น")
                return True
            self.open_shop_selector(player)
            return True

        if name == "bgshop":
            return self._handle_admin_command(sender, args)

        return False

    def _handle_admin_command(self, sender, args) -> bool:
        """จัดการคำสั่งย่อยของ /bgshop (parse เอง เพราะรับมาเป็น message)"""
        # รวม args ทั้งหมดแล้วแยกเป็น token ใหม่ (รองรับทั้งกรณีเป็น 1 string และหลาย element)
        tokens = " ".join(a for a in args if a is not None).split()
        if not tokens:
            self._send_help(sender)
            return True

        sub = tokens[0].lower()
        rest = tokens[1:]

        if sub == "reload":
            self._cmd_reload(sender)
        elif sub == "list":
            self._cmd_list(sender)
        elif sub == "createshop":
            self._cmd_createshop(sender, rest)
        elif sub == "delshop":
            self._cmd_delshop(sender, rest)
        elif sub == "additem":
            self._cmd_additem(sender, rest)
        elif sub == "delitem":
            self._cmd_delitem(sender, rest)
        elif sub == "setperm":
            self._cmd_setperm(sender, rest)
        else:
            self._send_help(sender)
        return True

    def _send_help(self, sender) -> None:
        lines = [
            f"{C_GOLD}=== คำสั่ง BGSHOP ===",
            f"{C_YELLOW}/shop {C_GRAY}- เปิดหน้าร้านค้า",
            f"{C_YELLOW}/bgshop reload {C_GRAY}- โหลดไฟล์ร้านค้าทั้งหมดใหม่",
            f"{C_YELLOW}/bgshop list {C_GRAY}- แสดงรายชื่อร้านทั้งหมด",
            f"{C_YELLOW}/bgshop createshop <ชื่อไฟล์> <ชื่อร้านที่แสดง> {C_GRAY}- สร้างร้านใหม่",
            f"{C_YELLOW}/bgshop delshop <ชื่อไฟล์> {C_GRAY}- ลบร้าน",
            f"{C_YELLOW}/bgshop additem <ชื่อร้าน> <ราคา> <money|point> {C_GRAY}- เพิ่มไอเทมในมือ",
            f"{C_YELLOW}/bgshop additem <ชื่อร้าน> <item_id> <จำนวน> <ราคา> <money|point> {C_GRAY}- เพิ่มด้วย id",
            f"{C_YELLOW}/bgshop delitem <ชื่อร้าน> <ลำดับไอเทม> {C_GRAY}- ลบไอเทม",
            f"{C_YELLOW}/bgshop setperm <ชื่อร้าน> <permission|none> {C_GRAY}- ตั้ง/ถอด permission",
        ]
        sender.send_message("\n".join(lines))

    # ---- คำสั่ง reload ----
    def _cmd_reload(self, sender) -> None:
        try:
            self._reload_shops()
            sender.send_message(f"{C_GREEN}โหลดร้านค้าใหม่เรียบร้อย ({len(self.shop_manager.shops)} ร้าน)")
        except Exception as exc:  # noqa: BLE001
            self.logger.error(f"reload ล้มเหลว: {exc}")
            sender.send_error_message(f"โหลดร้านค้าใหม่ล้มเหลว: {exc}")

    # ---- คำสั่ง list ----
    def _cmd_list(self, sender) -> None:
        shops = self.shop_manager.shops
        if not shops:
            sender.send_message(f"{C_GRAY}ยังไม่มีร้านค้า")
            return
        lines = [f"{C_GOLD}=== รายชื่อร้านค้า ({len(shops)}) ==="]
        for shop in shops.values():
            status = f"{C_GREEN}เปิด" if shop.enabled else f"{C_RED}ปิด"
            perm = shop.permission if shop.permission else "public"
            lines.append(
                f"{C_YELLOW}{shop.file_id} {C_GRAY}| {C_WHITE}{shop.shop_name} "
                f"{C_GRAY}| {status}{C_GRAY} | สิทธิ์: {perm} | {len(shop.items)} ไอเทม"
            )
        sender.send_message("\n".join(lines))

    # ---- คำสั่ง createshop ----
    def _cmd_createshop(self, sender, rest) -> None:
        if len(rest) < 2:
            sender.send_error_message("รูปแบบ: /bgshop createshop <ชื่อไฟล์> <ชื่อร้านที่แสดง>")
            return
        file_id = rest[0]
        display_name = " ".join(rest[1:])
        if not self.shop_manager.is_valid_file_id(file_id):
            sender.send_error_message("ชื่อไฟล์ใช้ได้เฉพาะ a-z A-Z 0-9 _ - เท่านั้น")
            return
        shop = self.shop_manager.create_shop(file_id, display_name)
        if shop is None:
            sender.send_error_message(f"สร้างร้านไม่สำเร็จ (อาจมีร้าน '{file_id}' อยู่แล้ว)")
            return
        sender.send_message(
            f"{C_GREEN}สร้างร้าน '{file_id}' ({display_name}) เรียบร้อย! "
            f"{C_GRAY}ใช้ /bgshop additem เพื่อเพิ่มไอเทม"
        )

    # ---- คำสั่ง delshop ----
    def _cmd_delshop(self, sender, rest) -> None:
        if len(rest) < 1:
            sender.send_error_message("รูปแบบ: /bgshop delshop <ชื่อไฟล์>")
            return
        file_id = rest[0]
        shop = self.shop_manager.get(file_id)
        if shop is None:
            sender.send_error_message(f"ไม่พบร้าน '{file_id}'")
            return
        if self.shop_manager.delete_shop(shop.file_id):
            sender.send_message(f"{C_GREEN}ลบร้าน '{shop.file_id}' เรียบร้อย")
        else:
            sender.send_error_message(f"ลบร้าน '{file_id}' ไม่สำเร็จ")

    # ---- คำสั่ง additem (รองรับ 2 รูปแบบ) ----
    def _cmd_additem(self, sender, rest) -> None:
        # รูปแบบ 1 (จากไอเทมในมือ): additem <ชื่อร้าน> <ราคา> <money|point>  => 3 token
        # รูปแบบ 2 (พิมพ์เอง):      additem <ชื่อร้าน> <item_id> <จำนวน> <ราคา> <money|point> => 5 token
        from endstone_bgshop.shop_manager import normalize_currency

        if len(rest) not in (3, 5):
            sender.send_error_message(
                "รูปแบบ:\n"
                "§e/bgshop additem <ชื่อร้าน> <ราคา> <money|point> §7(จากไอเทมในมือ)\n"
                "§e/bgshop additem <ชื่อร้าน> <item_id> <จำนวน> <ราคา> <money|point> §7(พิมพ์เอง)"
            )
            return

        shop = self.shop_manager.get(rest[0])
        if shop is None:
            sender.send_error_message(f"ไม่พบร้าน '{rest[0]}'")
            return

        if len(rest) == 3:
            # ---- จากไอเทมในมือ ----
            player = self._resolve_player(sender)
            if player is None:
                sender.send_error_message("รูปแบบนี้ต้องใช้ในเกม (ต้องถือไอเทมในมือ)")
                return
            held = player.inventory.item_in_main_hand
            if held is None or held.type is None:
                sender.send_error_message("คุณต้องถือไอเทมที่จะเพิ่มไว้ในมือก่อน")
                return
            try:
                item_id = held.type.id
            except Exception:  # noqa: BLE001
                item_id = str(held.type)
            amount = int(held.amount)
            price_str, currency_str = rest[1], rest[2]
        else:
            # ---- พิมพ์ item_id เอง ----
            item_id = rest[1].strip()
            try:
                amount = int(rest[2])
            except ValueError:
                sender.send_error_message("จำนวนต้องเป็นตัวเลข")
                return
            price_str, currency_str = rest[3], rest[4]

        # ตรวจราคา
        try:
            price = int(price_str)
        except ValueError:
            sender.send_error_message("ราคาต้องเป็นตัวเลข")
            return
        if amount <= 0 or price < 0:
            sender.send_error_message("จำนวนต้องมากกว่า 0 และราคาต้องไม่ติดลบ")
            return

        # ตรวจสกุลเงิน
        currency = normalize_currency(currency_str)
        if currency is None:
            sender.send_error_message("สกุลเงินต้องเป็น money หรือ point เท่านั้น")
            return

        # เพิ่มไอเทมเข้าร้าน แล้วบันทึกไฟล์ทันที
        new_item = {
            "name": f"§f{item_id} x{amount}",
            "item_id": item_id,
            "amount": amount,
            "price": price,
            "currency": currency,
            "icon": "",
            "description": "",
        }
        shop.items.append(new_item)
        if self.shop_manager.save(shop):
            unit = "💰 เงิน" if currency == "money" else "⭐ พอยต์"
            sender.send_message(
                f"{C_GREEN}เพิ่มไอเทมเข้าร้าน '{shop.file_id}' แล้ว: "
                f"{C_WHITE}{item_id} x{amount} {C_GRAY}ราคา {price} {unit}"
            )
        else:
            # บันทึกไม่สำเร็จ — ถอนออกเพื่อให้ข้อมูลในหน่วยความจำตรงกับไฟล์
            shop.items.pop()
            sender.send_error_message("บันทึกไฟล์ร้านไม่สำเร็จ ไม่ได้เพิ่มไอเทม")

    # ---- คำสั่ง delitem ----
    def _cmd_delitem(self, sender, rest) -> None:
        if len(rest) < 2:
            sender.send_error_message("รูปแบบ: /bgshop delitem <ชื่อร้าน> <ลำดับไอเทม>")
            return
        shop = self.shop_manager.get(rest[0])
        if shop is None:
            sender.send_error_message(f"ไม่พบร้าน '{rest[0]}'")
            return
        try:
            index = int(rest[1])
        except ValueError:
            sender.send_error_message("ลำดับไอเทมต้องเป็นตัวเลข (เริ่มจาก 1)")
            return
        # ผู้ใช้พิมพ์ลำดับเริ่มจาก 1
        if index < 1 or index > len(shop.items):
            sender.send_error_message(
                f"ลำดับไอเทมไม่ถูกต้อง (ร้านนี้มี {len(shop.items)} ไอเทม)"
            )
            return
        removed = shop.items.pop(index - 1)
        if self.shop_manager.save(shop):
            sender.send_message(
                f"{C_GREEN}ลบไอเทมลำดับ {index} ({removed.get('item_id')}) ออกจากร้าน '{shop.file_id}' แล้ว"
            )
        else:
            # rollback ถ้าบันทึกไม่ได้
            shop.items.insert(index - 1, removed)
            sender.send_error_message("บันทึกไฟล์ร้านไม่สำเร็จ ไม่ได้ลบไอเทม")

    # ---- คำสั่ง setperm ----
    def _cmd_setperm(self, sender, rest) -> None:
        if len(rest) < 2:
            sender.send_error_message("รูปแบบ: /bgshop setperm <ชื่อร้าน> <permission|none>")
            return
        shop = self.shop_manager.get(rest[0])
        if shop is None:
            sender.send_error_message(f"ไม่พบร้าน '{rest[0]}'")
            return
        perm_value = rest[1].strip()
        if perm_value.lower() in ("none", "public", "-", '""', "''"):
            # ถอด permission → เปิด public
            shop.permission = None
            msg = f"{C_GREEN}ร้าน '{shop.file_id}' เปิดเป็น public แล้ว (ทุกคนเข้าได้)"
        else:
            shop.permission = perm_value
            self._ensure_permission(perm_value, public=False)
            msg = f"{C_GREEN}ตั้ง permission ร้าน '{shop.file_id}' เป็น {C_YELLOW}{perm_value}"
        if self.shop_manager.save(shop):
            sender.send_message(msg)
        else:
            sender.send_error_message("บันทึกไฟล์ร้านไม่สำเร็จ")

    # ================================================================== #
    #  UI: หน้าเลือกร้าน
    # ================================================================== #
    def open_shop_selector(self, player: Player) -> None:
        """ActionForm เลือกร้าน — แสดงเฉพาะร้านที่ผู้เล่นมีสิทธิ์เข้า"""
        # กรองเฉพาะร้านที่ enabled และผู้เล่นมีสิทธิ์
        visible = [
            shop for shop in self.shop_manager.shops.values()
            if self._can_access(player, shop)
        ]

        if not visible:
            player.send_error_message("§cคุณยังไม่มีสิทธิ์เข้าร้านค้าใด ๆ")
            return

        form = ActionForm(
            title=f"{C_GOLD}ร้านค้า BGSHOP",
            content=f"{C_GRAY}เลือกร้านที่ต้องการเข้า:",
        )
        for shop in visible:
            icon = shop.icon or None
            # ใช้ factory เพื่อ bind ตัวแปร shop ให้ถูกต้อง (กันปัญหา closure ใน loop)
            form.add_button(
                f"{C_WHITE}{shop.shop_name}",
                icon=icon,
                on_click=self._make_open_shop(shop.file_id),
            )
        player.send_form(form)

    def _make_open_shop(self, file_id: str):
        """สร้าง callback เปิดร้านตาม file_id (bind ค่าให้แน่นอน)"""
        def _cb(player: Player) -> None:
            self.open_shop_items(player, file_id)
        return _cb

    # ================================================================== #
    #  UI: หน้ารายการไอเทมในร้าน
    # ================================================================== #
    def open_shop_items(self, player: Player, file_id: str) -> None:
        """ActionForm รายการไอเทม — เช็คสิทธิ์ซ้ำก่อนเปิด"""
        shop = self.shop_manager.get(file_id)
        if shop is None:
            player.send_error_message("§cร้านค้านี้ไม่มีอยู่แล้ว")
            return
        # เช็คสิทธิ์ซ้ำ (กันสิทธิ์ถูกถอดระหว่างเปิดฟอร์มค้าง)
        if not self._can_access(player, shop):
            player.send_error_message("§cคุณไม่มีสิทธิ์ใช้ร้านค้านี้!")
            return

        if not shop.items:
            player.send_error_message(f"§cร้าน '{shop.shop_name}' ยังไม่มีสินค้า")
            return

        form = ActionForm(
            title=f"{C_GOLD}{shop.shop_name}",
            content=f"{C_GRAY}เลือกสินค้าที่ต้องการซื้อ:",
        )
        for index, item in enumerate(shop.items):
            unit = "💰" if item["currency"] == "money" else "⭐"
            currency_name = "เงิน" if item["currency"] == "money" else "พอยต์"
            label = (
                f"{item.get('name') or item['item_id']}\n"
                f"{C_GRAY}ราคา {C_YELLOW}{item['price']} {unit} {currency_name}"
            )
            icon = item.get("icon") or None
            form.add_button(
                label,
                icon=icon,
                on_click=self._make_confirm_buy(shop.file_id, index),
            )
        player.send_form(form)

    def _make_confirm_buy(self, file_id: str, index: int):
        def _cb(player: Player) -> None:
            self.confirm_purchase(player, file_id, index)
        return _cb

    # ================================================================== #
    #  UI: หน้ายืนยันการซื้อ
    # ================================================================== #
    def confirm_purchase(self, player: Player, file_id: str, index: int) -> None:
        """MessageForm ยืนยันการซื้อ พร้อมยอดคงเหลือ (ถ้ามี)"""
        shop = self.shop_manager.get(file_id)
        if shop is None:
            player.send_error_message("§cร้านค้านี้ไม่มีอยู่แล้ว")
            return
        if not self._can_access(player, shop):
            player.send_error_message("§cคุณไม่มีสิทธิ์ใช้ร้านค้านี้!")
            return
        if index < 0 or index >= len(shop.items):
            player.send_error_message("§cสินค้านี้ไม่มีอยู่แล้ว")
            return

        item = shop.items[index]
        unit = "💰 เงิน" if item["currency"] == "money" else "⭐ พอยต์"

        content_lines = [
            f"{C_WHITE}สินค้า: {item.get('name') or item['item_id']}",
            f"{C_GRAY}ไอดี: {item['item_id']}",
            f"{C_GRAY}จำนวน: {C_WHITE}{item['amount']}",
            f"{C_GRAY}ราคา: {C_YELLOW}{item['price']} {unit}",
        ]
        if item.get("description"):
            content_lines.append(f"{C_GRAY}{item['description']}")

        # แสดงยอดคงเหลือถ้า API รองรับ
        balance = self._get_balance(player, item["currency"])
        if balance is not None:
            content_lines.append(f"{C_GRAY}ยอดคงเหลือ: {C_AQUA}{balance}")

        form = MessageForm(
            title=f"{C_GOLD}ยืนยันการซื้อ",
            content="\n".join(content_lines),
            button1=f"{C_GREEN}ยืนยันการซื้อ",
            button2=f"{C_RED}ยกเลิก",
            on_submit=self._make_purchase_submit(shop.file_id, index),
        )
        player.send_form(form)

    def _make_purchase_submit(self, file_id: str, index: int):
        def _cb(player: Player, selection) -> None:
            # selection == 0 คือปุ่มแรก (button1 = ยืนยัน)
            if int(selection) == 0:
                self.do_purchase(player, file_id, index)
        return _cb

    # ================================================================== #
    #  ตรรกะการซื้อจริง (หักก่อน-ให้ทีหลัง)
    # ================================================================== #
    def do_purchase(self, player: Player, file_id: str, index: int) -> None:
        shop = self.shop_manager.get(file_id)
        if shop is None:
            player.send_error_message("§cร้านค้านี้ไม่มีอยู่แล้ว")
            return
        # เช็คสิทธิ์ซ้ำอีกครั้งตอนกดยืนยัน
        if not self._can_access(player, shop):
            player.send_error_message("§cคุณไม่มีสิทธิ์ใช้ร้านค้านี้!")
            return
        if index < 0 or index >= len(shop.items):
            player.send_error_message("§cสินค้านี้ไม่มีอยู่แล้ว")
            return

        item = shop.items[index]
        currency = item["currency"]
        price = int(item["price"])
        amount = int(item["amount"])
        item_id = item["item_id"]

        # ตรวจว่า API รองรับสกุลเงินนี้ไหม (พอยต์อาจไม่มีจริง)
        if not self._currency_supported(currency):
            self.logger.error(
                f"EconomyCore ไม่รองรับสกุลเงิน '{currency}' (ขาดเมธอด has/remove) "
                f"— ไอเทม {item_id} ในร้าน {file_id}"
            )
            player.send_error_message("§cระบบเศรษฐกิจไม่รองรับสกุลเงินนี้ กรุณาแจ้งแอดมิน")
            return

        # --- 1) เช็คเงิน/พอยต์พอไหม ---
        try:
            if currency == "money":
                has_enough = self.economy.has_money(player, price)
            else:
                has_enough = self.economy.has_points(player, price)
        except Exception as exc:  # noqa: BLE001
            self.logger.error(f"ตรวจยอดเงิน/พอยต์ล้มเหลว: {exc}")
            player.send_error_message("§cทำรายการไม่สำเร็จ กรุณาลองใหม่")
            return

        if not has_enough:
            player.send_error_message("เงินไม่พอ!" if currency == "money" else "พอยต์ไม่พอ!")
            return

        # --- 2) หักเงิน/พอยต์ (หักก่อน-ให้ทีหลัง) ---
        try:
            if currency == "money":
                ok = self.economy.remove_money(player, price)
            else:
                ok = self.economy.remove_points(player, price)
        except Exception as exc:  # noqa: BLE001
            self.logger.error(f"หักเงิน/พอยต์ล้มเหลว: {exc}")
            player.send_error_message("§cทำรายการไม่สำเร็จ")
            return

        # ถ้า remove คืน False → ห้ามให้ไอเทมเด็ดขาด
        if ok is False:
            player.send_error_message("§cทำรายการไม่สำเร็จ")
            return

        # --- 3) หักสำเร็จแล้ว จึงให้ไอเทม ---
        try:
            item_stack = ItemStack(item_id, amount)
        except Exception as exc:  # noqa: BLE001
            # สร้าง ItemStack ไม่ได้ (item_id ผิด) → คืนเงินให้ผู้เล่น
            self.logger.error(f"สร้าง ItemStack '{item_id}' ไม่สำเร็จ: {exc}")
            self._refund(player, currency, price)
            player.send_error_message("§cไอเทมนี้มีปัญหา (item_id ไม่ถูกต้อง) คืนเงินให้แล้ว")
            return

        if not self._give_item(player, item_stack):
            # ให้ไอเทมไม่สำเร็จเลย (ทั้ง add และ drop ล้มเหลว) → คืนเงิน
            self._refund(player, currency, price)
            player.send_error_message("§cไม่สามารถมอบไอเทมได้ คืนเงินให้แล้ว")
            return

        # --- 4) แจ้งผลสำเร็จ ---
        unit = "💰 เงิน" if currency == "money" else "⭐ พอยต์"
        player.send_message(
            f"{C_GREEN}ซื้อสำเร็จ! {C_WHITE}{item.get('name') or item_id} x{amount} "
            f"{C_GRAY}(-{price} {unit})"
        )

    def _give_item(self, player: Player, item_stack: ItemStack) -> bool:
        """มอบไอเทมให้ผู้เล่น ถ้ากระเป๋าเต็ม → drop ที่ตำแหน่งผู้เล่น

        คืน True ถ้าไอเทมถึงมือผู้เล่น (เข้ากระเป๋า หรือ drop สำเร็จ)
        คืน False ถ้าล้มเหลวทั้งหมด (ผู้เรียกควรคืนเงิน)
        """
        try:
            leftover = player.inventory.add_item(item_stack)
        except Exception as exc:  # noqa: BLE001
            self.logger.error(f"เพิ่มไอเทมเข้ากระเป๋าล้มเหลว: {exc}")
            leftover = {0: item_stack}

        # leftover เป็น dict ของไอเทมที่ใส่ไม่หมด (กระเป๋าเต็ม)
        if not leftover:
            return True

        # กระเป๋าเต็ม → พยายาม drop ไอเทมที่เหลือที่ตำแหน่งผู้เล่น
        dropped_any = False
        try:
            location = player.location
            dimension = player.dimension
            for leftover_item in leftover.values():
                dimension.drop_item(location, leftover_item)
                dropped_any = True
            if dropped_any:
                player.send_message(f"{C_YELLOW}กระเป๋าเต็ม! ไอเทมถูกดรอปที่พื้นแล้ว")
                return True
        except Exception as exc:  # noqa: BLE001
            self.logger.error(f"ดรอปไอเทมล้มเหลว: {exc}")

        return False

    def _refund(self, player: Player, currency: str, price: int) -> None:
        """คืนเงิน/พอยต์ให้ผู้เล่น (ใช้เมื่อให้ไอเทมไม่สำเร็จหลังหักไปแล้ว)"""
        try:
            if currency == "money":
                self.economy.add_money(player, price)
            elif hasattr(self.economy, "add_points"):
                self.economy.add_points(player, price)
        except Exception as exc:  # noqa: BLE001
            self.logger.error(f"คืนเงิน/พอยต์ให้ {player.name} ไม่สำเร็จ: {exc}")
