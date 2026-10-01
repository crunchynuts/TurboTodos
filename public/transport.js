const bridgeReady = window.TURBO_DESKTOP ? new Promise(resolve => {
  if (window.pywebview?.api) resolve(window.pywebview.api);
  else window.addEventListener('pywebviewready', () => resolve(window.pywebview.api), {once:true});
}) : null;
export async function apiFetch(path, options={}) {
  if (!window.TURBO_DESKTOP) return fetch(path, {...options,body:options.body&&typeof options.body!=='string'?JSON.stringify(options.body):options.body});
  const api = await bridgeReady;
  const r = await api.request(options.method || 'GET', path, typeof options.body==='string'?JSON.parse(options.body):options.body||null);
  return {ok:r.status >= 200 && r.status < 300, json:async()=>r.body};
}
export const preferences = {
  getItem(key) {try {return localStorage.getItem(key);} catch {return null;}},
  setItem(key,value) {try {localStorage.setItem(key,value);} catch {}},
};
export async function saveDownload(blob, filename) {
  if (window.TURBO_DESKTOP) {
    const encoded = await new Promise((resolve,reject)=>{
      const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);
      reader.onerror=()=>reject(Error('Unable to prepare export'));reader.readAsDataURL(blob);
    });
    return (await bridgeReady).save_file(filename,encoded);
  }
  const url=URL.createObjectURL(blob), a=document.createElement('a');
  a.href=url;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);return true;
}
