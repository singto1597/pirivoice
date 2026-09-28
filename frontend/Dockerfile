# ==========================================
# Stage 1: Build Stage (ใช้ Node.js สำหรับคอมไพล์โค้ด)
# ==========================================
FROM node:22-alpine AS build-stage

# กำหนด Working Directory ภายใน Container
WORKDIR /app

# คัดลอก package.json และ package-lock.json (ถ้ามี) เข้ามาก่อน
# เพื่อใช้ประโยชน์จาก Docker Cache หากไม่ได้มีการเปลี่ยนแปลง Dependencies
COPY package*.json ./

# ติดตั้ง Dependencies ทั้งหมด
RUN npm install
ARG VITE_API_BASE_URL
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
# คัดลอก Source Code ทั้งหมดเข้าสู่ Container
COPY . .

# รันคำสั่งคอมไพล์ TypeScript และ Build โปรเจกต์ด้วย Vite
# ผลลัพธ์ที่ได้จะไปอยู่ในโฟลเดอร์ /app/dist
RUN npm run build


# ==========================================
# Stage 2: Production Stage (ใช้ Nginx สำหรับเสิร์ฟไฟล์ Static)
# ==========================================
FROM nginx:alpine AS production-stage

# ลบไฟล์ default ของ Nginx ออก (เพื่อเตรียมพื้นที่ให้ไฟล์ของเรา)
RUN rm -rf /usr/share/nginx/html/*

# คัดลอกเฉพาะโฟลเดอร์ dist จาก build-stage มาวางที่ root ของ Nginx
COPY --from=build-stage /app/dist /usr/share/nginx/html

# (สำคัญสำหรับ Vue Router) เพื่อให้การกด Refresh หน้าเว็บ (ที่ไม่ได้อยู่ที่ Root path) ไม่ติด 404
# ⚠️ ห้ามใช้ $uri/ — ถ้า path นั้นมีโฟลเดอร์จริงอยู่ (เช่น /playbooks/ ที่เก็บรูป) nginx จะ
#    จับว่าเป็น directory แล้วคืน 403 (ไม่มี index) แทนที่จะส่งต่อไปที่ SPA
#    ใช้แค่ try_files $uri /index.html → ไฟล์จริงถูกเสิร์ฟ, route ที่เหลือ fallback ไป SPA
#
# ⚠️ PWA (A1): `sw.js` + `manifest.json` **ต้องไม่ถูก cache** — ต่างจากไฟล์อื่นทั้งหมด
#    ถ้า cache ไว้ อัปเดต service worker รอบหน้าจะไม่มีผลเลยบนเครื่องที่ติดตั้งไปแล้ว
#    และจะหาสาเหตุไม่ได้ (เบราว์เซอร์ไม่ยอมโหลด sw.js ใหม่)
#    · /assets/* ไม่ต้องใส่ header — Vite ใส่ content hash ในชื่อไฟล์อยู่แล้ว
#    · index.html ไม่ต้องใส่ — `location /` ไม่ได้ให้ Cache-Control เลย ⇒ เบราว์เซอร์
#      ใช้ heuristic caching แต่ navigation ส่วนใหญ่ยิงผ่าน SW (network-first) อยู่แล้ว
RUN echo 'server { \
    listen 80; \
    server_name _; \
    root /usr/share/nginx/html; \
    index index.html; \
    location = /sw.js { \
        add_header Cache-Control "no-cache, must-revalidate"; \
        try_files $uri =404; \
    } \
    location = /manifest.json { \
        add_header Cache-Control "no-cache"; \
        try_files $uri =404; \
    } \
    location / { \
        try_files $uri /index.html; \
    } \
}' > /etc/nginx/conf.d/default.conf

# เปิดรับการเชื่อมต่อที่ Port 80
EXPOSE 80

# คำสั่งรัน Nginx ให้อยู่เบื้องหน้า (Foreground) เพื่อไม่ให้ Container ดับ
CMD ["nginx", "-g", "daemon off;"]
