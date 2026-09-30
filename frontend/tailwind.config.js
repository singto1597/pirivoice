/** @type {import('tailwindcss').Config} */
import daisyui from 'daisyui';

export default {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        // ฟอนต์หลัก 'Noto Sans Thai' (รองรับภาษาไทย) — fallback เป็น sans-serif เสมอ
        // กัน Google Fonts โหลดไม่ทัน/โดน block แล้วหลุดไปเป็น serif
        sans: ['"Noto Sans Thai"', 'sans-serif'],
        // พาดหัว/Display 'Anuphan' (จับคู่กับ Landing) — ใช้กับ headline/ตัวเลขใหญ่
        display: ['"Anuphan"', '"Noto Sans Thai"', 'sans-serif'],
      },

      // ============================================================
      // 🎨 Design token — **ที่เดียวที่นิยามสีของแบรนด์**
      //
      // ก่อนหน้านี้ `#B91C1C` / `#991B1B` ถูกฮาร์ดโค้ดเป็น arbitrary value
      // (`bg-[#B91C1C]`) กระจายอยู่ ~610 จุดใน 44 ไฟล์ ⇒ เปลี่ยนสีแบรนด์ทีต้องแก้ 610 ที่
      // และไม่มีอะไรกันไม่ให้พิมพ์ hex เพี้ยน (`#B91C1D`) แล้วไม่มีใครจับได้
      //
      // ⚠️ ค่า hex ตรงกับของเดิม **ทุกตัวอักษร** ⇒ การแทนที่ต้องไม่เปลี่ยนภาพแม้พิกเซลเดียว
      //
      // ⚠️ ชื่อบางตัวต่างจากร่างแผนเล็กน้อย (จงใจ):
      //    `bg` → `canvas`   เพราะ `bg-bg` อ่านไม่ออกว่าคืออะไร
      //    `*.bg` → `*.soft` เพราะ `bg-ok-bg` / `bg-danger-bg` อ่านซ้ำซ้อน
      //
      // ⚠️ `extend` = **รวม** กับพาเลตต์เดิม ไม่ใช่แทนที่ ⇒ `stone-*`, `emerald-*` ยังใช้ได้ปกติ
      // ============================================================
      colors: {
        /** แดงคาร์ดินัล — สีแบรนด์ · ใช้กับ "ปุ่มหลัก/สิ่งที่ต้องสนใจ" เท่านั้น */
        brand: {
          DEFAULT: '#B91C1C',
          strong: '#991B1B',
          tint: '#FEF2F2',
        },
        /** พื้นหลังหน้า (เทาอ่อน) — เดิมปนกัน 2 ค่า (#F5F5F7 / #FAFAF9) */
        canvas: '#F7F7F8',
        /** พื้นการ์ด/แถบ (ขาว) */
        surface: '#FFFFFF',
        /** เส้นขอบ 1px — แทนการใช้ stone-100/200/300 ปนกัน */
        line: '#E7E7EA',
        /**
         * สีตัวอักษร 3 ระดับ (contrast บนพื้นขาว ≥ 4.5:1 ทุกตัว)
         * ใช้แทน stone-900/600/400 ที่วันนี้ปนกันไปหมด
         */
        ink: {
          1: '#1F2328', // เนื้อหาหลัก / หัวข้อ
          2: '#5F6368', // รอง / คำอธิบาย
          3: '#8A8F98', // เมตาดาตา / เวลา (ห้ามใช้เป็นเนื้อหาสำคัญ)
        },
        /** สถานะ: สำเร็จ */
        ok: { DEFAULT: '#15803D', soft: '#F0FDF4' },
        /** สถานะ: เตือน / ใกล้ครบกำหนด */
        warn: { DEFAULT: '#B45309', soft: '#FFFBEB' },
        /** สถานะ: ผิดพลาด / อันตราย (ต่างจาก `brand` ที่เป็นสีแบรนด์) */
        danger: { DEFAULT: '#DC2626', soft: '#FEF2F2' },
      },

      /**
       * มุมโค้ง — 3 ระดับพอ (เดิมปนกัน `rounded-xl`/`2xl`/`3xl`/`full` ตามใจ)
       * `sheet` ใช้กับ bottom sheet ที่ติดขอบล่างเท่านั้น
       */
      borderRadius: {
        card: '16px',
        control: '12px',
        sheet: '24px',
      },

      /**
       * เงา — **อนุญาตแค่ 2 ตัวนี้** (ที่เหลือใช้เส้นขอบ 1px แทน ตามทิศทาง Editorial & Civic)
       * ถ้าต้องการเงาใหม่ ให้เพิ่มที่นี่พร้อมเหตุผล ไม่ใช่พิมพ์ arbitrary value ในไฟล์
       */
      boxShadow: {
        fab: '0 6px 16px rgba(185,28,28,.28)',
        sheet: '0 -8px 32px rgba(0,0,0,.14)',
      },

      /**
       * สเกลตัวอักษรสำหรับข้อความไทย — 4 ระดับ
       * ⚠️ ภาษาไทยต้องการ `letter-spacing: 0` และ **ห้าม `uppercase`** (ไม่มีตัวพิมพ์ใหญ่)
       */
      fontSize: {
        caption: ['12px', { lineHeight: '18px' }],
        body: ['16px', { lineHeight: '26px' }],
        'title-m': ['18px', { lineHeight: '28px' }],
        'title-l': ['22px', { lineHeight: '32px' }],
      },
    },
  },
  plugins: [
    daisyui,
  ],
  daisyui: {
    themes: false, // false = ใช้ default theme ไปก่อน (ปรับทีหลังได้)
  },
}
