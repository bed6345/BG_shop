# BGSHOP

ปลั๊กอินร้านค้าหลายร้านสำหรับ **Endstone 0.11.x** (ทดสอบบน endstone 0.11.4)
เชื่อมต่อระบบเศรษฐกิจผ่าน **EconomyCore** — หักได้ทั้ง **เงิน** และ **พอยต์** ตั้งค่าได้รายไอเทม
พร้อมระบบ **permission รายร้าน**

## คุณสมบัติ

- 🏪 **หลายร้านค้าไม่จำกัด** — 1 ร้าน = 1 ไฟล์ JSON ในโฟลเดอร์ `plugins/bgshop/shops/`
- 💰⭐ **หักได้ทั้งเงินและพอยต์** — ตั้ง `"currency": "money"` หรือ `"point"` ต่อไอเทม
- 🔒 **Permission รายร้าน** — ร้านที่ไม่มีสิทธิ์จะถูกซ่อนจากหน้าเลือกร้าน
- 🔁 **แก้ไฟล์ JSON แล้ว `/bgshop reload`** ได้ทันที ไม่ต้องรีสตาร์ท
- 🖐️ **เพิ่มไอเทมในเกม** — ทั้งจากไอเทมในมือและพิมพ์ item_id เอง
- ✅ **ปลอดภัย** — หักเงิน/พอยต์สำเร็จก่อน จึงมอบไอเทม (ถ้าหักไม่สำเร็จจะไม่ให้ไอเทม)

## การเชื่อมต่อ EconomyCore

BGSHOP **ไม่มี** ระบบเงินของตัวเอง แต่ดึง API ผ่าน Service Manager:

```python
self.economy = self.server.service_manager.load("EconomyCore")
# fallback: self.server.plugin_manager.get_plugin("economy_core").api
```

ต้องติดตั้งปลั๊กอิน `economy_core` ไว้ก่อน (ประกาศ `depend = ["economy_core"]`)

## คำสั่ง

| คำสั่ง | สิทธิ์ | หน้าที่ |
|---|---|---|
| `/shop` | `bgshop.use` (ทุกคน) | เปิดหน้าร้านค้า |
| `/bgshop reload` | `bgshop.admin` (OP) | โหลดไฟล์ร้านค้าใหม่ทั้งหมด |
| `/bgshop list` | OP | แสดงรายชื่อร้านทั้งหมด |
| `/bgshop createshop <ชื่อไฟล์> <ชื่อร้าน>` | OP | สร้างร้านใหม่ |
| `/bgshop delshop <ชื่อไฟล์>` | OP | ลบร้าน |
| `/bgshop additem <ชื่อร้าน> <ราคา> <money\|point>` | OP | เพิ่มไอเทมจากในมือ |
| `/bgshop additem <ชื่อร้าน> <item_id> <จำนวน> <ราคา> <money\|point>` | OP | เพิ่มไอเทมด้วย id |
| `/bgshop delitem <ชื่อร้าน> <ลำดับไอเทม>` | OP | ลบไอเทม (ลำดับเริ่มจาก 1) |
| `/bgshop setperm <ชื่อร้าน> <permission\|none>` | OP | ตั้ง/ถอด permission (`none` = public) |

> **หมายเหตุ:** `<ชื่อร้าน>` ในคำสั่งคือ **ชื่อไฟล์** (ไม่รวม `.json`) เช่น `general`

## Permission รายร้าน

- ร้านที่ตั้ง `"permission"` ใน JSON → แสดงเฉพาะผู้เล่นที่มีสิทธิ์นั้น (`player.has_permission`)
- ร้านที่ `"permission"` เป็น `""` / `null` → **public** ทุกคนเข้าได้
- OP ที่มี `bgshop.admin` → เข้าได้ทุกร้าน (bypass)
- การมอบสิทธิ์ให้ผู้เล่นทำผ่านปลั๊กอิน permission ภายนอก หรือคำสั่ง permission ของเซิร์ฟ

## โครงสร้างไฟล์ร้านค้า (`shops/general.json`)

```json
{
  "shop_name": "ร้านค้าทั่วไป",
  "icon": "textures/items/emerald",
  "enabled": true,
  "permission": "bgshop.shop.general",
  "items": [
    {
      "name": "§aเพชร x8",
      "item_id": "minecraft:diamond",
      "amount": 8,
      "price": 500,
      "currency": "money",
      "icon": "textures/items/diamond",
      "description": "เพชรคุณภาพดี"
    },
    {
      "name": "§bธาตุเนเธอไรต์",
      "item_id": "minecraft:netherite_ingot",
      "amount": 1,
      "price": 10,
      "currency": "point",
      "icon": "textures/items/netherite_ingot",
      "description": "ซื้อด้วยพอยต์เท่านั้น"
    }
  ]
}
```

- ถ้าโฟลเดอร์ `shops/` ว่าง จะสร้าง `general.json` ตัวอย่างให้อัตโนมัติ
- ถ้า JSON พัง จะข้ามไฟล์นั้นพร้อม log เตือน (ไม่ทำให้ปลั๊กอินล่ม)
- ไอเทมที่ขาด field จำเป็น (`item_id`, `amount`, `price`, `currency`) จะถูกข้ามพร้อม log

## การติดตั้ง / Build

```bash
pip install build
python -m build
# ได้ไฟล์ .whl ในโฟลเดอร์ dist/ นำไปวางในโฟลเดอร์ plugins/ ของเซิร์ฟเวอร์
```

## โครงสร้างโปรเจกต์

```
BG_shop/
├── pyproject.toml
├── README.md
└── src/
    └── endstone_bgshop/
        ├── __init__.py
        ├── plugin.py          # โค้ดหลัก (คำสั่ง, ฟอร์ม, ตรรกะการซื้อ)
        └── shop_manager.py    # โหลด/บันทึก/ตรวจสอบไฟล์ร้านค้า
```
