(()=>{'use strict';
const RULES={ServiceType:['','Firm','Firm - Variable','Interruptible'],EncumberedTag:['','No'],FwdMonthIncl:['Yes'],ValidEconDealType:['Yes'],InterruptCommTrans:['NO']};
const norm=v=>{const s=String(v??'').trim();return s==='(Blank)'?'':s;};
function apply(){const A=window.PNL_APP,D=window.PNL_DATA;if(!A?.state?.filters||!D?.dicts||typeof A.schedule!=='function'){console.error('Default filters not applied: dashboard API unavailable.');const n=document.createElement('div');n.textContent='Default filters could not be applied. Verify reporting scope before using totals.';n.style.cssText='padding:10px;background:#fff3cd;color:#664d03';document.body.prepend(n);return;}
const missing=[];
for(const [key,allowed] of Object.entries(RULES)){const values=D.dicts[key];if(!Array.isArray(values)){missing.push(key+' field missing');A.state.filters[key]=new Set();continue;}const selected=new Set();values.forEach((v,i)=>{if(allowed.includes(norm(v)))selected.add(i);});A.state.filters[key]=selected;if(!selected.size)missing.push(key+' has no matching default values');}
window.PNL_DEFAULT_FILTERS={version:'1.0',rules:RULES,applied:true,warnings:missing};
A.schedule();
if(missing.length){const n=document.createElement('div');n.textContent='Default filter warning: '+missing.join('; ')+'. Empty selections intentionally return no data.';n.style.cssText='padding:10px;background:#fff3cd;color:#664d03';document.body.prepend(n);}
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>requestAnimationFrame(apply));else requestAnimationFrame(apply);
})();