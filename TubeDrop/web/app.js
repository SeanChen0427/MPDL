const $=id=>document.getElementById(id);
let token=new URLSearchParams(location.hash.slice(1)).get('token')||sessionStorage.getItem('tubedrop-token')||'';
if(token)sessionStorage.setItem('tubedrop-token',token);
history.replaceState(null,'',location.pathname);
let format='mp4',lanUrl='',active=new Map(),busy=false,cloudMode=false;
const savedOptions=$('quality').innerHTML;
const platformNames={youtube:'YouTube',instagram:'Instagram',facebook:'Facebook'};
const urlHint='支援公開影片與 Reels；多影片貼文只下載第一支影片，不支援限時動態。';
function updateUrlHint(){let name='';try{const host=new URL($('url').value.trim()).hostname;name=/^(?:www\.|m\.|music\.)?youtube\.com$/.test(host)||host==='youtu.be'?'YouTube':/^(?:www\.|m\.)?instagram\.com$/.test(host)?'Instagram':/^(?:(?:www|m|mbasic|web|touch|[a-z]{2}-[a-z]{2})\.)?facebook\.com$/.test(host)||/^(?:www\.)?fb\.watch$/.test(host)?'Facebook':''}catch{}$('urlhint').textContent=(name?'已辨識 '+name+' · ':'')+urlHint}
$('url').addEventListener('input',updateUrlHint);
function toast(message){$('toast').textContent=message;$('toast').classList.remove('hidden');setTimeout(()=>$('toast').classList.add('hidden'),3500)}
function error(message){$('formerror').textContent=message;$('formerror').classList.toggle('hidden',!message)}
async function api(path,body){const res=await fetch(path,{method:body?'POST':'GET',credentials:'same-origin',headers:{'X-Access-Token':token,...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});const data=await res.json();if(!res.ok)throw Error(data.error||'連線失敗');return data}
document.querySelectorAll('[data-format]').forEach(button=>button.onclick=()=>{format=button.dataset.format;document.querySelectorAll('[data-format]').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));$('quality').innerHTML=format==='mp3'?'<option value="best">320 kbps · MP3</option>':savedOptions;$('quality').disabled=format==='mp3';$('qualitylabel').textContent=format==='mp3'?'音訊品質':'影片畫質';$('qualityhint').textContent=format==='mp3'?'以 320 kbps 轉出 MP3；實際音質仍受來源限制。':'依影片提供的畫質下載，不會放大低畫質來源。'});
$('paste').onclick=async()=>{try{if(!navigator.clipboard)throw Error();$('url').value=await navigator.clipboard.readText();updateUrlHint();$('url').focus()}catch{$('url').focus();toast('請長按輸入框貼上，或按 ⌘V／Ctrl+V')}};
$('share').onclick=async()=>{try{await navigator.clipboard.writeText(lanUrl);toast(cloudMode?'網址已複製，可在其他裝置開啟':'已複製，將網址傳到手機即可開啟')}catch{window.prompt(cloudMode?'複製這個網址，在其他裝置開啟：':'複製這個網址，在同一 Wi-Fi 的手機開啟：',lanUrl)}};
function render(job){let card=$('job-'+job.id);if(!card){$('empty')?.remove();card=document.createElement('article');card.className='job';card.id='job-'+job.id;card.innerHTML='<div class="jobhead"><div class="jobtitle"></div><span class="type"></span></div><div class="status" role="status"></div><div class="progress" role="progressbar" aria-label="目前下載階段進度" aria-valuemin="0" aria-valuemax="100"><span></span></div><div class="jobactions"></div><div class="detail"></div><details class="technical hidden"><summary>查看技術訊息</summary><pre></pre></details>';$('jobs').prepend(card)}card.querySelector('.jobtitle').textContent=job.title;card.querySelector('.type').textContent=(platformNames[job.platform]?platformNames[job.platform]+' · ':'')+job.format.toUpperCase();card.querySelector('.status').textContent=job.message+(job.size?' · '+(job.size/1024/1024).toFixed(1)+' MB':'');const progress=card.querySelector('.progress');progress.classList.toggle('hidden',['done','error','cancelled'].includes(job.state));progress.setAttribute('aria-valuenow',Math.round(job.progress));progress.firstElementChild.style.width=job.progress+'%';const actions=card.querySelector('.jobactions');actions.replaceChildren();if(job.state==='done'){const link=document.createElement('a');link.className='save';link.textContent='儲存 '+job.format.toUpperCase()+' 檔案';link.href='/files/'+job.id+(cloudMode?'':'?token='+encodeURIComponent(token));link.download=job.filename;actions.append(link)}else if(['running','queued'].includes(job.state)){const cancel=document.createElement('button');cancel.className='smallbutton';cancel.textContent='取消下載';cancel.onclick=async()=>{try{await api('/api/cancel/'+job.id,{});await poll(job.id)}catch(e){toast(e.message)}};actions.append(cancel)}card.querySelector('.detail').textContent=job.error||'';const technical=card.querySelector('.technical');technical.classList.toggle('hidden',!job.details||job.details===job.error);technical.querySelector('pre').textContent=job.details||'';if(['done','error','cancelled'].includes(job.state)){active.delete(job.id);saveActive()}}
function saveActive(){sessionStorage.setItem('tubedrop-jobs',JSON.stringify([...active.keys()]))}
async function poll(id){try{const job=await api('/api/jobs/'+id);render(job);return job}catch(e){if(e.message.includes('找不到')){active.delete(id);saveActive()}else{$('connection').textContent='連線中斷';$('connection').dataset.state='offline';error('無法連上下載服務，請稍後重新整理頁面。')}}}
$('form').onsubmit=async event=>{event.preventDefault();if(busy)return;busy=true;$('submit').disabled=true;error('');try{const job=await api('/api/jobs',{url:$('url').value.trim(),format,quality:$('quality').value});active.set(job.id,true);saveActive();await poll(job.id)}catch(e){error(e.message)}finally{busy=false;$('submit').disabled=false}};
async function init(){try{const status=await api('/api/status');cloudMode=status.mode==='cloud';$('connection').textContent=status.ready?(cloudMode?'已連接雲端':'已連接 Mac'):'元件準備中';$('connection').dataset.state=status.ready?'connected':'waiting';$('submit').disabled=!status.ready;lanUrl=cloudMode?location.origin+'/':status.lan_url;$('share').disabled=!lanUrl;if(cloudMode){$('workerhint').textContent='下載與轉檔由雲端處理';$('phoneheading').textContent='手機、電腦都能下載';$('phoneintro').textContent='開啟同一個網址，任何裝置、不同網路都能使用。下載記錄僅顯示在發起下載的瀏覽器。';document.querySelector('.share .tag-label').textContent='跨裝置使用';$('share').innerHTML='<svg aria-hidden="true"><use href="#i-copy"/></svg>複製工具網址';$('usagenote').textContent='請下載自己擁有或已獲授權的內容。檔案完成後暫存 1 小時，請及時儲存；服務重新啟動也會清除記錄。';}if(!status.ready)error('下載元件尚未就緒，請完成安裝後重新整理。');for(const id of JSON.parse(sessionStorage.getItem('tubedrop-jobs')||'[]')){active.set(id,true);await poll(id)}}catch(e){$('connection').textContent='尚未連線';$('connection').dataset.state='offline';error(e.message)}}
let polling=false;setInterval(async()=>{if(polling)return;polling=true;try{for(const id of [...active.keys()])await poll(id)}finally{polling=false}},1500);
const context=document.modelContext;
if(context?.registerTool){
  const lifecycle=new AbortController();
  window.addEventListener('pagehide',()=>lifecycle.abort(),{once:true});
  const inputSchema={type:'object',properties:{url:{type:'string'},format:{type:'string',enum:['mp4','mp3']}},required:['url','format'],additionalProperties:false};
  const prepare=async(input,youtubeOnly=false)=>{
    if(!input||typeof input.url!=='string'||!['mp4','mp3'].includes(input.format))throw Error('請提供影片網址及 mp4 或 mp3 格式');
    const data=await api('/api/prepare',{url:input.url,format:input.format});
    if(youtubeOnly&&data.platform!=='youtube')throw Error('請用 prepare_video_download 準備 IG 或 FB 影片');
    $('url').value=data.url;
    updateUrlHint();
    document.querySelector('[data-format="'+input.format+'"]').click();
    return{prepared:true,platform:data.platform,format:input.format};
  };
  for(const tool of [
    {name:'prepare_video_download',title:'準備影片下載',description:'填入 YouTube、Instagram（IG）或 Facebook（FB）的單支影片網址及 MP4 或 MP3 格式，供使用者檢查並按下開始下載。',execute:input=>prepare(input)},
    {name:'prepare_youtube_download',title:'準備 YouTube 下載',description:'填入 YouTube 網址及 MP4 或 MP3 格式，供使用者檢查並按下開始下載。',execute:input=>prepare(input,true)}
  ]){
    try{Promise.resolve(context.registerTool({...tool,annotations:{readOnlyHint:false,untrustedContentHint:false},inputSchema},{signal:lifecycle.signal})).catch(()=>{})}catch{}
  }
}

init();
$('backtotop').onclick=()=>window.scrollTo({top:0,behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});
