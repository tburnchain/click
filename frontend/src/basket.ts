// 비회원 상품 장바구니 — localStorage에 담아두고 가입 후 자동 반영
const KEY = "gamdap_basket";

export interface BasketItem { id: number; title: string; thumbnail_url: string | null; }

export function getBasket(): BasketItem[] {
  try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; }
}

function save(items: BasketItem[]) {
  localStorage.setItem(KEY, JSON.stringify(items));
  window.dispatchEvent(new Event("basket-change"));
}

export function inBasket(id: number): boolean {
  return getBasket().some((i) => i.id === id);
}

export function toggleBasket(item: BasketItem): boolean {
  const items = getBasket();
  const idx = items.findIndex((i) => i.id === item.id);
  if (idx >= 0) { items.splice(idx, 1); save(items); return false; }
  items.push(item); save(items); return true;
}

export function clearBasket() { save([]); }
