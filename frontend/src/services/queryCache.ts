import { reactive } from 'vue';
import { AxiosHeaders, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios';

/**
 * 🧠 Cache ของ GET ที่ชั้น axios — ทำให้หน้าเว็บ "จำค่าเก่า" ได้
 *
 * หลักการคือ **stale-while-revalidate**: ครั้งแรกยิงจริงแล้วเก็บผลไว้ ครั้งถัดไปที่
 * view mount ใหม่ (เช่นกดกลับมาหน้านี้) จะได้ `reactive()` proxy จาก cache **ทันที**
 * ⇒ ไม่มี skeleton/spinner กระพริบ แล้วยิงคำขอสดเบื้องหลัง พอ response กลับมาก็
 * `reconcile()` ทับ **ในที่เดียวกับ proxy เดิม** ⇒ view ที่ถือ reference อยู่แล้ว
 * (ref/computed) เห็นค่าใหม่อัตโนมัติโดยไม่ต้องแก้ `isLoading` ของตัวเอง
 *
 * ⚠️ **ข้อจำกัดที่สำคัญที่สุด** — cache นี้ทำให้ *object/array ที่ถูกยึด reference ไว้*
 *   อัปเดตเองได้ แต่ **primitive ที่ view คัดลอกออกมา** (`total.value = res.total`)
 *   จะไม่มีวันเปลี่ยน ⇒ ต้องอ่านผ่าน computed จาก response ที่ถือไว้ (ดู list views)
 *
 * 🔒 cache ผูกกับ access token ⇒ ผู้ใช้สองคนในแท็บเดียวกันเห็น cache กันไม่ได้
 *   และถูกล้างทุกครั้งที่ login/logout/401 (`clearQueryCache`)
 */

export interface CacheEntry {
  key: string;
  url: string;
  /** reactive proxy ของ response — reconcile จะ mutate ตัวนี้ */
  data: unknown;
  /** กัน revalidate ซ้ำซ้อนต่อ key เดียวกัน */
  revalidating: boolean;
  lastAccess: number;
}

/** 50 พอสำหรับมือถือ/แท็บเดียว — เกินกว่านี้เสี่ยงกินแรมโดยไม่จำเป็น */
const MAX_ENTRIES = 50;

/** Map รักษาลำดับการ insert ⇒ can evict oldest ได้โดยไม่ต้องมีโครงสร้างเพิ่ม */
const store = new Map<string, CacheEntry>();

/**
 * เวลา (ms) ที่ URL นี้ **ยิง network สำเร็จล่าสุด**
 *
 * ใช้กับป้าย "อัปเดตล่าสุด" — ถ้าอ่านจาก `new Date()` ตอน load แท็บที่ได้ cache Hit
 * จะโกหกว่าข้อมูลเพิ่งอัปเดตทั้งที่ยังไม่ได้ยิง • reactive Map ⇒ computed ที่อ่านค่านี้
 * ถูก recompute ตอน revalidate เสร็จ
 */
const syncedAt = reactive(new Map<string, number>());

export function markSynced(url: string): void {
  syncedAt.set(url, Date.now());
}

export function getSyncedAt(url: string): number | null {
  return syncedAt.get(url) ?? null;
}

/** คีย์ที่อาจทำให้เกิด prototype pollution — ห้ามเขียนลง response object */
const BLOCKED_KEYS = new Set(['__proto__', 'constructor', 'prototype']);

/**
 * stringify แบบเรียงคีย์ ⇒ `{ a, b }` กับ `{ b, a }` ได้ key เดียวกัน
 * (params ที่จัดเรียงลำดับต่างกันไม่ควรกลายเป็น cache คนละชุด)
 */
function stableStringify(value: unknown): string {
  if (value === undefined) return 'undefined';
  if (value === null) return 'null';
  if (value instanceof Date) return JSON.stringify(value.toISOString());
  if (typeof value !== 'object') return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(',')}]`;
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record).sort();
  return `{${keys.map((k) => `${JSON.stringify(k)}:${stableStringify(record[k])}`).join(',')}}`;
}

export function buildCacheKey(url: string, params: unknown, token: string | null): string {
  return JSON.stringify([token, url, stableStringify(params)]);
}

/**
 * ชื่อ resource แรกหลัง `/api/` (ข้าม `v1`/`v2`)
 * `PATCH /api/issues/3/resolve` → `issues`
 *
 * ⚠️ ต้องเทียบ **segment เต็ม** ไม่ใช่ `startsWith` — `/api/issues-extra` ต้องไม่เท่ากับ
 *   `/api/issues` ไม่งั้นการลบ cache จะลามข้าม resource
 */
function resourceOf(url: string): string | null {
  const match = /^\/api\/(?:v\d+\/)?([^/?#]+)/.exec(url);
  return match?.[1] ?? null;
}

/** อ่าน entry + แตะ LRU */
export function getCacheEntry(key: string): CacheEntry | undefined {
  const entry = store.get(key);
  if (entry) entry.lastAccess = Date.now();
  return entry;
}

function evictOverflow(): void {
  while (store.size > MAX_ENTRIES) {
    let oldestKey: string | null = null;
    let oldestAccess = Number.POSITIVE_INFINITY;
    for (const [key, entry] of store) {
      if (entry.lastAccess < oldestAccess) {
        oldestAccess = entry.lastAccess;
        oldestKey = key;
      }
    }
    if (oldestKey === null) return;
    store.delete(oldestKey);
  }
}

/**
 * เขียนผลลัพธ์ลง cache
 *
 * ⚠️ ถ้ามี entry อยู่แล้ว (แข่งขันกันตอน miss) ให้ **reconcile เข้า entry เดิม** แล้วคืน
 *   entry เดิม — ไม่สร้าง proxy ตัวที่สองที่ไม่มีใครถือ reference
 */
export function writeCache(key: string, url: string, data: unknown): CacheEntry {
  // reactive() คืน proxy เดิมถ้าเป็น reactive อยู่แล้ว ⇒ เรียกซ้ำได้ปลอดภัย
  const fresh = reactive(data as object) as unknown;
  const existing = store.get(key);
  if (existing) {
    reconcile(existing.data, fresh);
    existing.lastAccess = Date.now();
    return existing;
  }
  const entry: CacheEntry = {
    key,
    url,
    data: fresh,
    revalidating: false,
    lastAccess: Date.now(),
  };
  store.set(key, entry);
  evictOverflow();
  return entry;
}

/**
 * entry ยังเป็นตัวที่อยู่ใน store อยู่ไหม?
 * ใช้กัน revalidate ที่เริ่มก่อน mutation: ถ้า mutation ลบ entry ไปแล้วระหว่างรอ response
 * ⇒ ห้ามเอาข้อมูลเก่าเขียนทับ
 */
export function isCurrentEntry(key: string, entry: CacheEntry): boolean {
  return store.get(key) === entry;
}

export function deleteCacheEntry(key: string): void {
  store.delete(key);
}

/**
 * ล้าง cache ของ resource เดียวกับ mutation ที่เพิ่งสำเร็จ
 * เช่น PATCH `/api/issues/3/resolve` → ลบ `/api/issues…` แต่ไม่แตะ `/api/boards…`
 */
export function invalidateForMutation(url: string | undefined): void {
  if (!url) return;
  const resource = resourceOf(url);
  if (!resource) return;
  for (const [key, entry] of store) {
    if (resourceOf(entry.url) === resource) store.delete(key);
  }
}

export function clearQueryCache(): void {
  store.clear();
  syncedAt.clear();
}

/** response ที่จะถูก cache ได้ต้องเป็น object/array — string/null ปล่อยผ่านไม่เก็บ */
export function isCacheableData(data: unknown): boolean {
  return typeof data === 'object' && data !== null;
}

function isMergeable(value: unknown): value is object {
  return typeof value === 'object' && value !== null;
}

/**
 * Deep merge **in-place** จาก `source` ทับ `target` โดยรักษา object/array identity
 *
 * - array: จับคู่ตาม index แล้ว recurse · ตัดส่วนเกินด้วย splice · ต่อส่วนที่เพิ่ม
 * - object: อัปเดตคีย์ที่มี · เพิ่มคีย์ใหม่ · ลบคีย์ที่หายไปจาก source
 *
 * 🔑 identity ต้องคงอยู่ เพราะ view ถือ reference ของ proxy นี้ไว้แล้ว (ผ่าน ref/computed)
 */
export function reconcile(target: unknown, source: unknown): void {
  if (Array.isArray(target) && Array.isArray(source)) {
    const shared = Math.min(target.length, source.length);
    for (let i = 0; i < shared; i += 1) {
      const current = target[i];
      const next = source[i];
      if (isMergeable(current) && isMergeable(next) && Array.isArray(current) === Array.isArray(next)) {
        reconcile(current, next);
      } else if (current !== next) {
        target[i] = next;
      }
    }
    if (source.length < target.length) target.splice(source.length);
    else if (source.length > target.length) {
      for (let i = target.length; i < source.length; i += 1) target.push(source[i]);
    }
    return;
  }

  if (isMergeable(target) && isMergeable(source) && !Array.isArray(target) && !Array.isArray(source)) {
    const current = target as Record<string, unknown>;
    const next = source as Record<string, unknown>;
    for (const key of Object.keys(next)) {
      if (BLOCKED_KEYS.has(key)) continue;
      const currentValue = current[key];
      const nextValue = next[key];
      if (
        isMergeable(currentValue) &&
        isMergeable(nextValue) &&
        Array.isArray(currentValue) === Array.isArray(nextValue)
      ) {
        reconcile(currentValue, nextValue);
      } else if (currentValue !== nextValue) {
        current[key] = nextValue;
      }
    }
    for (const key of Object.keys(current)) {
      if (!(key in next) && !BLOCKED_KEYS.has(key)) delete current[key];
    }
  }
}

/**
 * ตอบกลับเสมือน adapter ของ axios (ใช้แทน network ตอน cache hit)
 *
 * ⚠️ ต้องครบทุกฟิลด์ของ `AxiosResponse` — axios `dispatchRequest` ยังรัน
 *   `transformResponse` **หลัง** adapter แต่ transform แตะเฉพาะ string
 *   ⇒ object/reactive-proxy จะถูกปล่อยผ่านไปโดยไม่ถูกแปลง
 */
export function makeCachedResponse<T>(
  config: InternalAxiosRequestConfig,
  data: T,
): AxiosResponse<T> {
  return {
    data,
    status: 200,
    statusText: 'OK',
    headers: new AxiosHeaders(),
    config,
    request: {},
  };
}

declare module 'axios' {
  interface AxiosRequestConfig {
    /** ปิด cache สำหรับคำขอนี้ (polling, ฟอร์มแก้ไข, ค่าที่ต้องสด) */
    noCache?: boolean;
  }
  interface InternalAxiosRequestConfig {
    /** true = response นี้มาจาก cache (adapter ถูกแทน) */
    __fromCache?: boolean;
    /** key ของ cache entry สำหรับขาเข้า (ใช้ schedule revalidate) */
    __cacheKey?: string;
  }
}
