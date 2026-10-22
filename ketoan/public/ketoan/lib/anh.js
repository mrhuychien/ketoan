// anh.js — NÉN ảnh chụp trước khi gửi: ảnh điện thoại 4–12 MB còn ~0,5 MB, gửi được cả khi
// sóng trong kho yếu. Ảnh phiếu trả về mang CHỮ SỐ VIẾT TAY phải đọc lại trên máy tính, nên giữ
// cạnh dài 2400px — không bóp xuống 1200px như ảnh chứng từ giao hàng bên vận chuyển.

export function nenAnh(file, maxDim = 2400, quality = 0.85) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const k = Math.min(1, maxDim / Math.max(img.naturalWidth, img.naturalHeight));
      const c = document.createElement("canvas");
      c.width = Math.round(img.naturalWidth * k);
      c.height = Math.round(img.naturalHeight * k);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      c.toBlob((b) => (b ? resolve(b) : reject(new Error("Nén ảnh thất bại"))), "image/jpeg", quality);
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Không đọc được ảnh"));
    };
    img.src = url;
  });
}

// File / Blob → base64 (bỏ đầu "data:…;base64,") — gửi trong JSON như các màn upload khác của app.
export function base64(blob) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result).split(",").pop());
    r.onerror = () => reject(new Error("Không đọc được file"));
    r.readAsDataURL(blob);
  });
}

// Ảnh chụp → {content: base64 JPEG đã nén, ten}. Trình duyệt không vẽ được (HEIC trên vài máy)
// thì gửi bản gốc — server soát chữ ký đầu file, không phải ảnh nó nhận được thì báo rõ.
export async function anhGui(file) {
  try {
    const b = await nenAnh(file);
    return { content: await base64(b), ten: (file.name || "anh").replace(/\.[^.]+$/, "") + ".jpg" };
  } catch (e) {
    return { content: await base64(file), ten: file.name || "anh" };
  }
}
