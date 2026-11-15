import { createPortal } from "react-dom";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { ArrowUp, Check, ChevronUp, CloudOff, ImagePlus, Loader2, Monitor, MessageSquarePlus, MousePointerClick, Palette, PanelRightClose, PanelRightOpen, Redo2, Smartphone, Sparkles, Undo2, X } from "lucide-react";
import { toast } from "sonner";
import { Button, Field, Modal, cx } from "./ui";
import { post } from "../lib/api";
import { useApi } from "../lib/hooks";
import { ACCEPT_IMAGES, UploadTile } from "./References";

/*
 * Runs inside the page being edited (a sandboxed iframe with no access to AIMVA). Click text to type, click an image
 * to swap it, and a small toolbar offers bold/italic, size, link and the page's own colours. Hovering a section offers
 * move, copy, remove, background colour and "Ask AI". It talks to the app only via postMessage. Everything it adds is
 * marked data-ae-* / data-aimva-editor and stripped before saving.
 */
const EDITOR_JS = String.raw`(function(){
var TEXT='h1,h2,h3,h4,h5,h6,p,li,a,button,figcaption,blockquote,summary,label,td,th,dt,dd,small,span';
var SECTION='[data-aimva-section],section,header,footer,aside';
var undo=[],redo=[],editing=null,hoverSec=null,target=null,ids=0,bgOpen=false,fxOpen=false,cmode=false;
var css=document.createElement('style');css.setAttribute('data-aimva-editor','');
css.textContent='[data-ae-hover]{outline:2px dashed rgba(11,107,103,.55)!important;outline-offset:-2px}'+
'[data-ae-target]{outline:3px solid #00696b!important;outline-offset:-3px}'+
'[contenteditable=true]{outline:2px solid #00696b!important;outline-offset:3px;cursor:text;min-width:1em}'+
'[data-ae-text]:hover{outline:1px solid rgba(0,105,107,.45);outline-offset:2px;cursor:text}img{cursor:pointer}img:hover{outline:3px solid #00696b;outline-offset:-3px}'+
'.ae-bar{position:absolute;z-index:2147483647;display:flex;align-items:center;gap:2px;background:#0f282f;border-radius:999px;padding:4px;box-shadow:0 8px 24px rgba(0,0,0,.3);font:600 12px/1 system-ui,sans-serif;max-width:calc(100vw - 16px);flex-wrap:wrap}'+
'.ae-bar button{all:unset;color:#fff;padding:7px 10px;border-radius:999px;cursor:pointer;white-space:nowrap}.ae-bar button:hover{background:rgba(255,255,255,.16)}'+
'.ae-bar .ae-sw{width:18px;height:18px;padding:0;margin:0 3px;border-radius:50%;box-shadow:0 0 0 2px rgba(255,255,255,.35)}.ae-bar .ae-sw:hover{box-shadow:0 0 0 2px #fff}'+
'[data-ae-drop=before]{box-shadow:0 -4px 0 #00696b!important}[data-ae-drop=after]{box-shadow:0 4px 0 #00696b!important}[data-ae-dragging]{opacity:.45}'+
'[data-ae-img]{outline:3px solid #00696b!important;outline-offset:-3px}'+
'.ae-handle{position:absolute;z-index:2147483646;width:16px;height:16px;background:#00696b;border:2px solid #fff;border-radius:4px;cursor:nwse-resize;touch-action:none;box-shadow:0 2px 8px rgba(0,0,0,.3)}'+
'.ae-bar .ae-grip{cursor:grab;touch-action:none}'+
'html[data-ae-cmode],html[data-ae-cmode] *{cursor:crosshair!important}html[data-ae-cmode] [data-ae-text]:hover,html[data-ae-cmode] img:hover{outline:none!important}'+
'.ae-bar .ae-sep{width:1px;height:18px;background:rgba(255,255,255,.2);margin:0 3px}.ae-bar .ae-ai{background:#00696b}.ae-bar .ae-ai:hover{background:#007f81}';
document.head.appendChild(css);
function send(m){parent.postMessage(Object.assign({aimva:1},m),'*')}
function state(){send({type:'history',undo:undo.length,redo:redo.length})}
function snap(){undo.push(document.body.innerHTML);if(undo.length>60)undo.shift();redo=[];state()}
function changed(){send({type:'dirty'})}
function bar(id){var b=document.getElementById(id);if(!b){b=document.createElement('div');b.id=id;b.className='ae-bar';b.setAttribute('data-aimva-editor','');document.body.appendChild(b)}return b}
function place(b,el,inside){var r=el.getBoundingClientRect();b.style.top=Math.max(4,window.scrollY+r.top+(inside?8:-46))+'px';b.style.left=(inside?Math.max(8,window.scrollX+r.right-b.offsetWidth-8):Math.max(8,Math.min(window.scrollX+r.left,window.scrollX+document.documentElement.clientWidth-b.offsetWidth-8)))+'px'}
function hide(id){var b=document.getElementById(id);if(b)b.style.display='none'}
function hasForm(el){return !!(el.matches&&el.matches('form[data-aimva-lead]'))||!!el.querySelector('form[data-aimva-lead]')}
function v(n){return getComputedStyle(document.documentElement).getPropertyValue(n).trim()}
function palette(){var out=[];[v('--p')||v('--dk'),v('--a')||v('--gd'),'#111827','#6b7280','#ffffff'].forEach(function(c){if(c&&out.indexOf(c)<0)out.push(c)});return out}
function rgb(c){var d=document.createElement('div');d.style.color=c;document.body.appendChild(d);var m=getComputedStyle(d).color.match(/\d+(\.\d+)?/g)||[0,0,0];d.remove();return m.map(Number)}
function readableOn(c){var x=rgb(c).slice(0,3).map(function(n){n/=255;return n<=.03928?n/12.92:Math.pow((n+.055)/1.055,2.4)});var L=.2126*x[0]+.7152*x[1]+.0722*x[2];return L>.45?'#111827':'#ffffff'}
function filled(el){var bg=getComputedStyle(el).backgroundColor;return bg&&bg!=='transparent'&&!/rgba\(.*,\s*0\)$/.test(bg)}
function btn(b,label,title,fn,cls){var x=document.createElement('button');x.textContent=label;x.title=title;if(cls)x.className=cls;x.onmousedown=function(e){e.preventDefault();e.stopPropagation();fn()};b.appendChild(x);return x}
function sep(b){var s=document.createElement('span');s.className='ae-sep';b.appendChild(s)}
function swatches(b,apply,reset){palette().forEach(function(c){var x=btn(b,'','Use this colour',function(){apply(c)},'ae-sw');x.style.background=c});btn(b,'↺','Back to the original colour',reset)}
function label(sec){var h=sec.querySelector('h1,h2,h3');var t=(h?h.textContent:'').replace(/\s+/g,' ').trim();return t?t.slice(0,48):(sec.getAttribute('data-aimva-section')||sec.tagName.toLowerCase())}
function setTarget(sec,lbl){if(target)target.removeAttribute('data-ae-target');target=sec;if(!sec){send({type:'target',id:null});return}
  if(!sec.getAttribute('data-ae-sid'))sec.setAttribute('data-ae-sid','s'+(++ids));sec.setAttribute('data-ae-target','');send({type:'target',id:sec.getAttribute('data-ae-sid'),label:lbl||label(sec)})}
function sectionBar(sec){var b=bar('ae-sec');b.innerHTML='';
  if(bgOpen){swatches(b,function(c){snap();sec.style.background=c;sec.style.color=readableOn(c);changed()},function(){snap();sec.style.background='';sec.style.color='';changed()});sep(b);btn(b,'Done','Close colours',function(){bgOpen=false;sectionBar(sec)})}
  else if(fxOpen){btn(b,'Darker','Darken the background (keeps text readable)',function(){overlay(sec,15)});btn(b,'Lighter','Lighten the background',function(){overlay(sec,-15)});sep(b);
    btn(b,'Flat','No shadow',function(){shadow(sec,0)});btn(b,'Lifted','Soft shadow',function(){shadow(sec,1)});btn(b,'Floating','Deep shadow',function(){shadow(sec,2)});sep(b);
    btn(b,(sec.style.position==='sticky'?'✓ ':'')+'Stays on screen','Keep this section on screen while the page scrolls (good for a top bar)',function(){pin(sec);sectionBar(sec)});
    btn(b,(sec.style.backgroundAttachment==='fixed'?'✓ ':'')+'Background stays still','The background stays put while the content scrolls over it',function(){still(sec);sectionBar(sec)});sep(b);
    btn(b,'Done','Close effects',function(){fxOpen=false;sectionBar(sec)})}
  else{
  btn(b,'↑','Move up',function(){var p=sec.previousElementSibling;if(p&&!p.hasAttribute('data-aimva-editor')){snap();sec.parentNode.insertBefore(sec,p);changed()}});
  btn(b,'↓','Move down',function(){var n=sec.nextElementSibling;if(n&&!n.hasAttribute('data-aimva-editor')){snap();sec.parentNode.insertBefore(n,sec);changed()}});
  btn(b,'Copy','Duplicate section',function(){if(hasForm(sec)){send({type:'notice',text:'The lead form section can only appear once.'});return}snap();var c=sec.cloneNode(true);c.removeAttribute('data-ae-sid');c.removeAttribute('data-ae-target');c.removeAttribute('data-ae-hover');sec.after(c);changed()});
  btn(b,'Remove','Remove section',function(){if(hasForm(sec)){send({type:'notice',text:"The lead form can't be removed: it's how visitors reach you."});return}snap();if(target===sec)setTarget(null);sec.remove();hide('ae-sec');changed()});
  sep(b);btn(b,'Colour','Background colour',function(){bgOpen=true;sectionBar(sec)});btn(b,'Effects','Depth, darkness and scrolling',function(){fxOpen=true;sectionBar(sec)});
  btn(b,'+ Image','Add an image to this section',function(){if(!sec.getAttribute('data-ae-sid'))sec.setAttribute('data-ae-sid','s'+(++ids));send({type:'add-image',sid:sec.getAttribute('data-ae-sid')})});
  btn(b,'✨ Ask AI','Change this section by describing it',function(){setTarget(sec)},'ae-ai')}
  b.style.display='flex';place(b,sec,true)}
function textBar(el){var b=bar('ae-txt');b.innerHTML='';
  btn(b,'B','Bold',function(){document.execCommand('bold')});btn(b,'I','Italic',function(){document.execCommand('italic')});
  btn(b,'A−','Smaller',function(){size(el,.9)});btn(b,'A+','Bigger',function(){size(el,1.1)});sep(b);
  btn(b,'⇤','Align left',function(){align(el,'left')});btn(b,'↔','Centre',function(){align(el,'center')});btn(b,'⇥','Align right',function(){align(el,'right')});
  btn(b,'↑','Move up',function(){step(el,-1)});btn(b,'↓','Move down',function(){step(el,1)});grip(b,el);sep(b);
  var fill=el.matches('a,button')&&filled(el);
  swatches(b,function(c){colorText(el,c,fill)},function(){snap();el.style.color='';el.style.backgroundColor='';el.querySelectorAll('span[style]').forEach(function(x){x.style.color='';x.style.fontSize=''});changed()});
  var a=el.closest('a');if(a){sep(b);btn(b,'Link','Where this goes',function(){if(!a.getAttribute('data-ae-id'))a.setAttribute('data-ae-id',String(++ids));send({type:'link',id:a.getAttribute('data-ae-id'),href:a.getAttribute('href')||''})})}
  sep(b);var sec=el.closest(SECTION);btn(b,'✨ Ask AI','Select words to change only those, or change this whole section',function(){var sel=selIn(el);if(sel){var sp=wrapSel(sel);stop();setTarget(sp,'“'+sp.textContent.trim().slice(0,40)+'”')}else if(sec){stop();setTarget(sec)}},'ae-ai');
  btn(b,'Delete','Delete this text',function(){snap();var t=el;stop();t.remove();changed()});btn(b,'Done','Finish editing',function(){stop()});
  b.style.display='flex';place(b,el,false)}
function block(el){var b=el;while(b.parentElement&&b.parentElement!==document.body&&b.parentElement.children.length===1&&!b.parentElement.matches(SECTION))b=b.parentElement;return b}
function step(el,dir){var b=block(el),o=dir<0?b.previousElementSibling:b.nextElementSibling;if(!o||o.hasAttribute('data-aimva-editor'))return;snap();dir<0?b.parentNode.insertBefore(b,o):b.parentNode.insertBefore(o,b);changed();refresh(el)}
function align(el,a){snap();if(el.tagName==='IMG'){el.style.display='block';el.style.marginLeft=a==='left'?'0':'auto';el.style.marginRight=a==='right'?'0':'auto'}else el.style.textAlign=a;changed();refresh(el)}
function refresh(el){setTimeout(function(){var t=document.getElementById('ae-txt'),i=document.getElementById('ae-img');if(t&&t.style.display!=='none')place(t,el,false);if(i&&i.style.display!=='none'){place(i,el,false);handle(el)}},0)}
function grip(b,el){var g=btn(b,'⠿ Move','Drag to move it up or down',function(){},'ae-grip');g.onmousedown=null;g.onpointerdown=function(e){e.preventDefault();e.stopPropagation();drag(el,e)}}
function drag(el,e0){var b=block(el),par=b.parentNode,drop=null,where=null;b.setAttribute('data-ae-dragging','');stop();hide('ae-sec');
  function clear(){if(drop)drop.removeAttribute('data-ae-drop')}
  function mv(e){var x=document.elementFromPoint(e.clientX,e.clientY);clear();drop=null;while(x&&x.parentNode!==par)x=x.parentNode;if(!x||x===b||x.nodeType!==1||x.hasAttribute('data-aimva-editor'))return;
    var r=x.getBoundingClientRect();where=e.clientY<r.top+r.height/2?'before':'after';drop=x;x.setAttribute('data-ae-drop',where);
    if(e.clientY<40)window.scrollBy(0,-20);else if(e.clientY>window.innerHeight-40)window.scrollBy(0,20)}
  function up(){document.removeEventListener('pointermove',mv);document.removeEventListener('pointerup',up);b.removeAttribute('data-ae-dragging');
    if(drop){clear();snap();where==='before'?par.insertBefore(b,drop):drop.after(b);changed()}
    if(el.tagName==='IMG')imageBar(el);else hide('ae-txt')}
  document.addEventListener('pointermove',mv);document.addEventListener('pointerup',up)}
var imgSel=null,imgFx=false;
function unselectImg(){imgFx=false;if(imgSel)imgSel.removeAttribute('data-ae-img');imgSel=null;hide('ae-img');var h=document.getElementById('ae-handle');if(h)h.style.display='none'}
function width(img,pct){snap();img.style.width=pct+'%';img.style.maxWidth='100%';img.style.height='auto';changed();refresh(img)}
function imageBar(img){if(imgSel&&imgSel!==img){imgSel.removeAttribute('data-ae-img');imgFx=false}imgSel=img;img.setAttribute('data-ae-img','');var b=bar('ae-img');b.innerHTML='';
  if(imgFx){btn(b,'☀−','Darker',function(){fx(img,'b',-10)});btn(b,'☀+','Brighter',function(){fx(img,'b',10)});btn(b,'◐−','Less contrast',function(){fx(img,'c',-10)});btn(b,'◐+','More contrast',function(){fx(img,'c',10)});sep(b);
    btn(b,'Flat','No shadow',function(){shadow(img,0)});btn(b,'Lifted','Soft shadow',function(){shadow(img,1)});btn(b,'Floating','Deep shadow',function(){shadow(img,2)});
    btn(b,'Round','Rounded corners',function(){snap();img.style.borderRadius=img.style.borderRadius?'':'16px';changed()});sep(b);
    btn(b,'Reset','Remove all effects',function(){snap();img.style.filter='';img.style.boxShadow='';img.style.borderRadius='';img.removeAttribute('data-fx-b');img.removeAttribute('data-fx-c');changed()});
    btn(b,'Back','Back to image tools',function(){imgFx=false;imageBar(img)});b.style.display='flex';place(b,img,false);handle(img);return}
  btn(b,'Replace','Pick another image',function(){if(!img.getAttribute('data-ae-id'))img.setAttribute('data-ae-id',String(++ids));send({type:'image',id:img.getAttribute('data-ae-id'),alt:img.alt||''})});sep(b);
  [['S',33],['M',50],['L',75],['Full',100]].forEach(function(x){btn(b,x[0],'Width '+x[1]+'%',function(){width(img,x[1])})});sep(b);
  btn(b,'⇤','Align left',function(){align(img,'left')});btn(b,'↔','Centre',function(){align(img,'center')});btn(b,'⇥','Align right',function(){align(img,'right')});sep(b);
  btn(b,'↑','Move up',function(){step(img,-1)});btn(b,'↓','Move down',function(){step(img,1)});grip(b,img);sep(b);
  btn(b,'Effects','Brightness, contrast, shadow',function(){imgFx=true;imageBar(img)});btn(b,'Done','Finish',unselectImg);b.style.display='flex';place(b,img,false);handle(img)}
function handle(img){var h=document.getElementById('ae-handle');if(!h){h=document.createElement('div');h.id='ae-handle';h.className='ae-handle';h.title='Drag to resize';h.setAttribute('data-aimva-editor','');document.body.appendChild(h);
    h.onpointerdown=function(e){e.preventDefault();e.stopPropagation();var t=imgSel;if(!t)return;snap();var pw=(t.parentElement||document.body).getBoundingClientRect().width||1,left=t.getBoundingClientRect().left;
      function mv(ev){var pct=Math.max(10,Math.min(100,Math.round((ev.clientX-left)/pw*100)));t.style.width=pct+'%';t.style.maxWidth='100%';t.style.height='auto';var r=t.getBoundingClientRect();h.style.left=(window.scrollX+r.right-8)+'px';h.style.top=(window.scrollY+r.bottom-8)+'px'}
      function up(){document.removeEventListener('pointermove',mv);document.removeEventListener('pointerup',up);changed();refresh(t)}
      document.addEventListener('pointermove',mv);document.addEventListener('pointerup',up)}}
  var r=img.getBoundingClientRect();h.style.display='block';h.style.left=(window.scrollX+r.right-8)+'px';h.style.top=(window.scrollY+r.bottom-8)+'px'}
function selIn(el){var s=window.getSelection();return s&&s.rangeCount&&!s.isCollapsed&&el.contains(s.anchorNode)&&el.contains(s.focusNode)?s:null}
function wrapSel(sel){var r=sel.getRangeAt(0),sp=document.createElement('span');sp.appendChild(r.extractContents());r.insertNode(sp);sel.removeAllRanges();var nr=document.createRange();nr.selectNodeContents(sp);sel.addRange(nr);return sp}
function size(el,f){var sel=selIn(el);snap();var t=el;if(sel){var px0=parseFloat(getComputedStyle(sel.anchorNode.nodeType===1?sel.anchorNode:sel.anchorNode.parentElement).fontSize)||16;t=wrapSel(sel);t.style.fontSize=Math.max(10,Math.min(120,Math.round(px0*f)))+'px'}
  else{var px=parseFloat(getComputedStyle(el).fontSize)||16;el.style.fontSize=Math.max(10,Math.min(120,Math.round(px*f)))+'px'}changed();var b=document.getElementById('ae-txt');if(b)place(b,el,false)}
function colorText(el,c,fill){var sel=selIn(el);snap();if(sel&&!fill){wrapSel(sel).style.color=c}else if(fill){el.style.backgroundColor=c;el.style.color=readableOn(c)}else el.style.color=c;changed()}
var SHADOWS=['none','0 6px 18px -6px rgba(0,0,0,.25)','0 24px 60px -18px rgba(0,0,0,.45)'];
function fx(el,k,d){snap();var b=+(el.getAttribute('data-fx-b')||100),c=+(el.getAttribute('data-fx-c')||100);
  if(k==='b')b=Math.max(30,Math.min(170,b+d));if(k==='c')c=Math.max(30,Math.min(200,c+d));
  el.setAttribute('data-fx-b',b);el.setAttribute('data-fx-c',c);el.style.filter=(b===100&&c===100)?'':'brightness('+b+'%) contrast('+c+'%)';changed()}
function shadow(el,i){snap();el.style.boxShadow=SHADOWS[i]==='none'?'':SHADOWS[i];changed()}
function overlay(sec,d){snap();var o=+(sec.getAttribute('data-fx-o')||0);o=Math.max(-60,Math.min(80,o+d));sec.setAttribute('data-fx-o',o);
  sec.style.boxShadow=o===0?'':'inset 0 0 0 4000px rgba('+(o>0?'0,0,0,':'255,255,255,')+(Math.abs(o)/100)+')';if(o>=30)sec.style.color='#ffffff';if(o<=-30)sec.style.color='#111827';changed()}
function pin(sec){snap();var on=sec.style.position==='sticky';sec.style.position=on?'':'sticky';sec.style.top=on?'':'0';sec.style.zIndex=on?'':'30';if(!on&&!filled(sec))sec.style.background=getComputedStyle(document.body).backgroundColor||'#fff';changed()}
function still(sec){snap();var on=sec.style.backgroundAttachment==='fixed';sec.style.backgroundAttachment=on?'':'fixed';changed();if(!on&&getComputedStyle(sec).backgroundImage==='none')send({type:'notice',text:'“Background stays still” shows once this section has a background photo. Ask AI: “use my photo as this section’s background”.'})}
function stop(){if(!editing)return;var el=editing;editing=null;el.removeAttribute('contenteditable');hide('ae-txt');if(el.__before!==el.innerHTML){changed()}}
function editable(el){if(!el||el.closest('[data-aimva-editor]'))return null;var t=el.closest(TEXT);if(!t)return null;if(t.matches('span')&&t.parentElement&&t.parentElement.closest(TEXT))t=t.parentElement.closest(TEXT);if(!t.textContent.trim())return null;return t}
function mark(root){root.querySelectorAll(TEXT).forEach(function(el){if(el.textContent.trim())el.setAttribute('data-ae-text','')})}
mark(document);
document.addEventListener('submit',function(e){e.preventDefault()},true);
document.addEventListener('mouseover',function(e){if(cmode||editing||imgSel||e.target.closest('[data-aimva-editor]'))return;var s=e.target.closest(SECTION);if(s&&s!==hoverSec){if(hoverSec)hoverSec.removeAttribute('data-ae-hover');hoverSec=s;bgOpen=false;fxOpen=false;s.setAttribute('data-ae-hover','');sectionBar(s)}});
document.addEventListener('click',function(e){if(e.target.closest('[data-aimva-editor]'))return;
  if(cmode){e.preventDefault();e.stopPropagation();var cs=e.target.closest(SECTION)||e.target.closest('body > *');if(!cs)return;if(!cs.getAttribute('data-ae-sid'))cs.setAttribute('data-ae-sid','s'+(++ids));
    var lt=(e.target.closest('h1,h2,h3,h4,p,li,a,button,img,label')||cs);var lb=lt.tagName==='IMG'?'the picture'+(lt.alt?' “'+lt.alt.slice(0,40)+'”':''):'“'+(lt.textContent||'').replace(/\s+/g,' ').trim().slice(0,60)+'”';
    send({type:'comment',id:cs.getAttribute('data-ae-sid'),label:lb,section:label(cs),x:e.clientX,y:e.clientY+window.scrollY});return}
  if(e.target.tagName==='IMG'){e.preventDefault();stop();hide('ae-sec');imageBar(e.target);return}
  unselectImg();
  var t=editable(e.target);if(t&&!e.target.closest('input,textarea,select')){e.preventDefault();if(editing===t)return;stop();snap();editing=t;t.__before=t.innerHTML;t.setAttribute('contenteditable','true');t.focus();hide('ae-sec');textBar(t);return}
  if(e.target.closest('a'))e.preventDefault();stop()},true);
document.addEventListener('keydown',function(e){if(editing&&e.key==='Escape'){stop()}if(editing&&e.key==='Enter'&&!e.shiftKey&&!editing.matches('p,li,blockquote,dd')){e.preventDefault();stop()}
  if(!editing&&(e.metaKey||e.ctrlKey)&&e.key.toLowerCase()==='z'){e.preventDefault();e.shiftKey?doRedo():doUndo()}});
document.addEventListener('paste',function(e){if(!editing)return;e.preventDefault();var t=(e.clipboardData||window.clipboardData).getData('text/plain');document.execCommand('insertText',false,t)});
function restore(h){unselectImg();document.body.innerHTML=h;hoverSec=null;target=document.querySelector('[data-ae-target]');if(!target)send({type:'target',id:null});changed();state()}
function doUndo(){stop();var h=undo.pop();if(h!==undefined){redo.push(document.body.innerHTML);restore(h)}}
function doRedo(){stop();var h=redo.pop();if(h!==undefined){undo.push(document.body.innerHTML);restore(h)}}
var ATTRS=['contenteditable','data-ae-hover','data-ae-id','data-ae-text','data-ae-sid','data-ae-target','data-ae-img','data-ae-drop','data-ae-dragging'];
function strip(root){root.querySelectorAll('[data-aimva-editor]').forEach(function(n){n.remove()});
  root.querySelectorAll(ATTRS.map(function(a){return '['+a+']'}).join(',')).forEach(function(n){ATTRS.forEach(function(a){n.removeAttribute(a)})});
  if(root.removeAttribute)ATTRS.forEach(function(a){root.removeAttribute(a)});return root}
function clean(){return '<!doctype html>\n'+strip(document.documentElement.cloneNode(true)).outerHTML}
window.addEventListener('scroll',function(){if(cmode)send({type:'scroll',y:window.scrollY})},{passive:true});
window.addEventListener('message',function(e){if(e.source!==parent)return;var m=e.data||{};
  if(m.type==='comment-mode'){cmode=!!m.on;stop();unselectImg();hide('ae-sec');if(hoverSec){hoverSec.removeAttribute('data-ae-hover');hoverSec=null}if(cmode)document.documentElement.setAttribute('data-ae-cmode','');else document.documentElement.removeAttribute('data-ae-cmode');send({type:'scroll',y:window.scrollY});return}
  if(m.type==='set-image'){var img=document.querySelector('img[data-ae-id="'+m.id+'"]');if(img){snap();img.src=m.src;img.removeAttribute('srcset');if(m.alt!==undefined)img.alt=m.alt;changed()}}
  else if(m.type==='insert-image'){var sc=document.querySelector('[data-ae-sid="'+m.sid+'"]');if(sc){snap();var box=sc.children.length===1&&sc.firstElementChild.children.length?sc.firstElementChild:sc;
    var im=document.createElement('img');im.src=m.src;im.alt=m.alt||'';im.style.cssText='display:block;width:100%;max-width:100%;height:auto;border-radius:12px;margin:16px auto';box.appendChild(im);changed();im.scrollIntoView({block:'center',behavior:'smooth'});setTimeout(function(){imageBar(im)},350)}}
  else if(m.type==='set-link'){var a=document.querySelector('a[data-ae-id="'+m.id+'"]');if(a){snap();a.setAttribute('href',m.href);changed()}}
  else if(m.type==='set-var'){snap();document.documentElement.style.setProperty(m.name,m.value);changed()}
  else if(m.type==='undo'){doUndo()}
  else if(m.type==='redo'){doRedo()}
  else if(m.type==='clear-target'){setTarget(null)}
  else if(m.type==='get-section'){var s=document.querySelector('[data-ae-sid="'+m.id+'"]');send({type:'section',id:m.id,html:s?strip(s.cloneNode(true)).outerHTML:null})}
  else if(m.type==='replace-section'){var old=document.querySelector('[data-ae-sid="'+m.id+'"]');if(!old)return;stop();snap();var tpl=document.createElement('template');tpl.innerHTML=m.html;
    var first=tpl.content.firstElementChild;if(!first)return;var nodes=Array.prototype.slice.call(tpl.content.childNodes);nodes.forEach(function(n){old.parentNode.insertBefore(n,old)});old.remove();
    hide('ae-sec');hoverSec=null;mark(first.parentNode||document);setTarget(first);first.scrollIntoView({block:'nearest',behavior:'smooth'});changed()}
  else if(m.type==='serialize'){stop();send({type:'html',html:clean()})}});
send({type:'ready',vars:{main:v('--p')?'--p':v('--dk')?'--dk':null,accent:v('--a')?'--a':v('--gd')?'--gd':null,mainValue:v('--p')||v('--dk'),accentValue:v('--a')||v('--gd')}});
})();`;

const SCRIPT_RE = /<script\b[\s\S]*?<\/script\s*>/gi;

/** Swap the page's own scripts for markers while editing (they'd run otherwise), and put them back on save. */
function prepare(html) {
  const scripts = [];
  let doc = html.replace(SCRIPT_RE, (m) => `<!--aimva-script-${scripts.push(m) - 1}-->`);
  const tag = `<script data-aimva-editor>${EDITOR_JS}</script>`;
  doc = /<\/body>/i.test(doc) ? doc.replace(/<\/body>/i, `${tag}</body>`) : doc + tag;
  return { doc, scripts };
}

const isHex = (v) => /^#[0-9a-f]{6}$/i.test(v || "");
const PALETTES = [["#6366f1", "#22d3ee"], ["#0f3d2e", "#c8a24a"], ["#13294b", "#d4a640"], ["#1f2937", "#f97316"], ["#7c2d5c", "#f4b860"],
  ["#0f766e", "#facc15"], ["#be123c", "#fb7185"], ["#111827", "#38bdf8"]];
const AUTOSAVE_MS = 1200;
const AI_IDEAS = ["Make this section shorter and punchier", "Add 3 FAQs about booking a visit", "Make it feel more premium", "Translate this section to Hindi"];

/** Your generated images first (they're what you made for this), then uploads and Brand Kit, plus "create a new one". */
function ImageChooser({ value, onChange }) {
  const { data: assets, setData: setAssets } = useApi("/api/content/assets?kind=image", []);
  const { data: refs, setData: setRefs } = useApi("/api/references?kind=image", []);
  const { data: brand } = useApi("/api/brand");
  const [prompt, setPrompt] = useState("");
  const [making, setMaking] = useState(false);
  const generated = assets.filter((a) => a.url).slice(0, 24).map((a) => ({ ref: `asset:${a.id}`, url: a.url, title: a.prompt }));
  const own = [...refs.map((r) => ({ ref: r.ref, url: r.url, title: "Upload" })),
    ...(brand?.images || []).map((i) => ({ ref: `brand:${i.id}`, url: i.url, title: "Brand Kit" }))];
  const create = async (e) => {
    e.preventDefault();
    if (prompt.trim().length < 3) return;
    setMaking(true);
    try {
      const [a] = await post("/api/content/image", { prompt: prompt.trim(), size: "16:9", use_brand: true });
      setAssets((all) => [a, ...all]);
      onChange(`asset:${a.id}`);
      setPrompt("");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setMaking(false);
    }
  };
  const Tile = ({ i }) => (
    <button type="button" onClick={() => onChange(i.ref)} title={i.title} aria-pressed={value === i.ref}
      className={cx("aspect-[4/3] overflow-hidden rounded-xl bg-surface-2 ring-2 transition", value === i.ref ? "ring-brand" : "ring-transparent hover:ring-line-strong")}>
      <img src={i.url} alt={i.title || ""} className="h-full w-full object-cover" loading="lazy" />
    </button>
  );
  return (
    <div className="space-y-4">
      <form onSubmit={create} className="rounded-2xl bg-lavender/50 p-3">
        <p className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-strong"><ImagePlus className="size-4 text-brand" /> Create a new image</p>
        <div className="flex gap-2">
          <input className="input h-10 flex-1" value={prompt} onChange={(e) => setPrompt(e.target.value)} maxLength={500} disabled={making}
            placeholder="e.g. Sunlit living room of a modern 3BHK apartment" aria-label="Describe the image" />
          <Button type="submit" busy={making} disabled={prompt.trim().length < 3}>Create</Button>
        </div>
        <p className="mt-1.5 text-xs text-muted">Uses your Brand Kit style. It's saved to your images too.</p>
      </form>
      {generated.length > 0 && (
        <div>
          <p className="label">Your generated images</p>
          <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">{generated.map((i) => <Tile key={i.ref} i={i} />)}</div>
        </div>
      )}
      <div>
        <p className="label">Uploads & Brand Kit</p>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          <UploadTile accept={ACCEPT_IMAGES} className="aspect-[4/3]" onUploaded={(r) => { setRefs((all) => [r, ...all]); onChange(r.ref); }} />
          {own.map((i) => <Tile key={i.ref} i={i} />)}
        </div>
      </div>
    </div>
  );
}

/**
 * The full-screen page editor: the page itself is the editor. Edits autosave (and merge into one version while you
 * keep working). `left` and `right` are the host's own top-bar items (back, name, publish…).
 */
const VisualEditor = forwardRef(function VisualEditor({ html, siteId, page, onSave, onPageReplaced, left, right, changes }, ref) {
  // The changes panel stays folded or open the way the owner left it (per browser).
  const [panelOpen, setPanelOpen] = useState(() => { try { return localStorage.getItem("aimva_changes_panel") !== "folded"; } catch { return true; } });
  const togglePanel = () => setPanelOpen((o) => { try { localStorage.setItem("aimva_changes_panel", o ? "folded" : "open"); } catch { /* private window */ } return !o; });
  const [sheet, setSheet] = useState(false);  // phones: the changes list as a sheet; the prompt box stays visible
  const frame = useRef(null);
  const askBox = useRef(null);
  const { doc, scripts } = useMemo(() => prepare(html), [html]);
  const [view, setView] = useState("desktop");
  const [status, setStatus] = useState("saved");  // saved | dirty | saving | error
  const [hist, setHist] = useState({ undo: 0, redo: 0 });
  const [vars, setVars] = useState(null);
  const [design, setDesign] = useState(false);
  const [picking, setPicking] = useState(null);  // {id, alt}
  const [linking, setLinking] = useState(null);  // {id, href}
  const [imgRef, setImgRef] = useState("");
  const [imgLink, setImgLink] = useState("");
  const [target, setTarget] = useState(null);  // {id, label}: the section Ask AI will change
  const [ask, setAsk] = useState("");
  // Comment mode: click a spot on the page, leave a Claude-style comment, and AI changes that section.
  const [commenting, setCommenting] = useState(false);
  const [note, setNote] = useState(null);  // {id, label, section, x, y, text, busy}
  const [scrollY, setScrollY] = useState(0);
  const [asking, setAsking] = useState(false);
  const waiters = useRef({});  // pending replies from the page, by message type
  const timer = useRef(null);
  const saving = useRef(Promise.resolve());
  // The owner's words for a section change, sent with the next autosave so Changes shows what they asked.
  const asked_ = useRef("");

  const send = useCallback((m) => frame.current?.contentWindow?.postMessage(m, "*"), []);
  const request = useCallback((m, reply) => new Promise((resolve) => { waiters.current[reply] = resolve; send(m); }), [send]);

  const dirtyN = useRef(0);  // edits made so far
  const savedN = useRef(0);  // edits included in the last save
  const schedule = useCallback(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => flushRef.current().catch(() => {}), AUTOSAVE_MS);
  }, []);
  const flush = useCallback(async () => {
    clearTimeout(timer.current);
    await saving.current;
    if (dirtyN.current === savedN.current) return;
    const n = dirtyN.current;
    const run = (async () => {
      setStatus("saving");
      try {
        const out = await request({ type: "serialize" }, "html");
        const asked = asked_.current;
        await onSave(out, asked);
        if (asked_.current === asked) asked_.current = "";
        savedN.current = n;
        if (dirtyN.current === n) setStatus("saved");
        else { setStatus("dirty"); schedule(); }
      } catch (e) {
        setStatus("error");
        toast.error(`Couldn't save: ${e.message}`);
        throw e;
      }
    })();
    saving.current = run.catch(() => {});
    return run;
  }, [request, onSave, schedule]);
  const flushRef = useRef(flush);
  flushRef.current = flush;
  useImperativeHandle(ref, () => ({ flush: () => flushRef.current(), dirty: () => dirtyN.current !== savedN.current }), []);

  useEffect(() => {
    const onMessage = (e) => {
      if (e.source !== frame.current?.contentWindow || !e.data?.aimva) return;
      const m = e.data;
      if (m.type === "ready") setVars(m.vars);
      else if (m.type === "dirty") {
        dirtyN.current += 1;
        setStatus("dirty");
        schedule();
      } else if (m.type === "history") setHist({ undo: m.undo, redo: m.redo });
      else if (m.type === "notice") toast.info(m.text);
      else if (m.type === "image") { setPicking({ id: m.id, alt: m.alt }); setImgRef(""); setImgLink(""); }
      else if (m.type === "add-image") { setPicking({ sid: m.sid, alt: "" }); setImgRef(""); setImgLink(""); }
      else if (m.type === "link") setLinking({ id: m.id, href: m.href });
      else if (m.type === "comment") setNote((n) => (n?.busy ? n : { id: m.id, label: m.label, section: m.section, x: m.x, y: m.y, text: "" }));
      else if (m.type === "scroll") setScrollY(m.y);
      else if (m.type === "target") {
        setTarget(m.id ? { id: m.id, label: m.label } : null);
        if (m.id) setTimeout(() => askBox.current?.focus(), 30);
      } else if (m.type === "html" || m.type === "section") {
        const out = m.type === "html" ? m.html.replace(/<!--aimva-script-(\d+)-->/g, (_, i) => scripts[Number(i)] || "") : m.html;
        waiters.current[m.type]?.(out);
        delete waiters.current[m.type];
      }
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [doc, scripts, schedule]);

  useEffect(() => {
    const warn = (e) => { if (status !== "saved") { e.preventDefault(); e.returnValue = ""; } };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [status]);
  useEffect(() => () => clearTimeout(timer.current), []);
  useEffect(() => {  // clicks inside the page don't reach this document: close the colours panel when focus moves into it
    if (!design) return;
    const close = () => setDesign(false);
    window.addEventListener("blur", close);
    return () => window.removeEventListener("blur", close);
  }, [design]);

  const applyImage = async () => {
    try {
      const { src } = await post("/api/sites/embed-image", { ref: imgRef || imgLink.trim() });
      send(picking.sid ? { type: "insert-image", sid: picking.sid, src, alt: picking.alt } : { type: "set-image", id: picking.id, src, alt: picking.alt });
      setPicking(null);
    } catch (e) {
      toast.error(e.message);
    }
  };
  const setColor = (name, value) => {
    setVars((v) => ({ ...v, [name === v.main ? "mainValue" : "accentValue"]: value }));
    send({ type: "set-var", name, value });
  };
  const applyPalette = ([main, accent]) => {
    if (vars?.main) send({ type: "set-var", name: vars.main, value: main });
    if (vars?.accent) send({ type: "set-var", name: vars.accent, value: accent });
    setVars((v) => ({ ...v, mainValue: main, accentValue: accent }));
  };

  const toggleComments = () => {
    const on = !commenting;
    setCommenting(on);
    setNote(null);
    send({ type: "comment-mode", on });
  };
  const runNote = async (e) => {
    e?.preventDefault();
    const n = note;
    if (!n || n.text.trim().length < 3 || n.busy) return;
    setNote({ ...n, busy: true });
    try {
      const section = await request({ type: "get-section", id: n.id }, "section");
      if (!section) throw new Error("That part of the page is gone. Click it again.");
      const out = await post(`/api/sites/${siteId}/ai-edit`, { instruction: `${n.text.trim()} (This is about ${n.label} in this section.)`, section });
      send({ type: "replace-section", id: n.id, html: out.section });
      asked_.current = n.text.trim();
      send({ type: "clear-target" });
      setNote(null);
      toast.success("Done. Undo if you don't like it.");
    } catch (err) {
      toast.error(err.message);
      setNote((x) => (x ? { ...x, busy: false } : x));
    }
  };

  const runAsk = async (e) => {
    e?.preventDefault();
    const instruction = ask.trim();
    if (instruction.length < 3 || asking) return;
    setAsking(true);
    try {
      if (target) {
        const section = await request({ type: "get-section", id: target.id }, "section");
        if (!section) throw new Error("That section is gone. Click a section again.");
        const out = await post(`/api/sites/${siteId}/ai-edit`, { instruction, section });
        send({ type: "replace-section", id: target.id, html: out.section });
        asked_.current = instruction;
        toast.success("Done. Undo if you don't like it.");
      } else {
        await flush();
        const out = await post(`/api/sites/${siteId}/ai-edit`, { instruction, ...(page ? { page } : {}) });
        onPageReplaced(out.site);
      }
      setAsk("");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setAsking(false);
    }
  };

  const StatusIcon = { saved: Check, dirty: Loader2, saving: Loader2, error: CloudOff }[status];
  const statusText = { saved: "Saved", dirty: "Saving…", saving: "Saving…", error: "Not saved" }[status];
  const hasColors = vars && (isHex(vars.mainValue) || isHex(vars.accentValue));

  const askForm = (inPanel) => (
    <form onSubmit={runAsk} className={cx("bg-surface", inPanel ? "border-t border-line p-3" : "border-t border-line px-3 py-2.5 sm:px-4")}>
          <div className={cx("flex flex-col gap-2", !inPanel && "mx-auto max-w-3xl")}>
            <div className="flex items-center gap-2 text-xs text-muted">
              <button type="button" onClick={toggleComments} aria-pressed={commenting} title="Click any spot on the page and say what to change"
                className={cx("inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 font-semibold", commenting ? "bg-brand text-white" : "bg-surface-2 text-strong hover:bg-lavender")}>
                <MessageSquarePlus className="size-3.5" /> {commenting ? "Commenting · click the page" : "Comment"}
              </button>
              {commenting ? <span className="truncate">Click any spot, say what should change, press Enter.</span> : target ? (
                <span className="inline-flex items-center gap-1.5 rounded-full bg-lavender px-2.5 py-1 font-medium text-strong">
                  Changing: {target.label}
                  <button type="button" aria-label="Change the whole page instead" onClick={() => send({ type: "clear-target" })} className="text-muted hover:text-strong"><X className="size-3.5" /></button>
                </span>
              ) : (
                <span className={cx("hidden items-center gap-1.5", !inPanel && "sm:flex")}><MousePointerClick className="size-3.5 text-brand" /> Click text to type · click an image to resize, move or swap it · hover a section for colour, order or <b className="text-ink">✨ Ask AI</b></span>
              )}
              {!ask && !commenting && !inPanel && <span className="hidden min-w-0 flex-1 gap-1.5 overflow-hidden lg:flex">{AI_IDEAS.slice(0, target ? 3 : 2).map((x) => (
                <button key={x} type="button" className="shrink-0 whitespace-nowrap rounded-full bg-surface-2 px-2.5 py-1 hover:bg-lavender" onClick={() => { setAsk(x); askBox.current?.focus(); }}>{x}</button>
              ))}</span>}
            </div>
            <div className="flex items-center gap-2 rounded-2xl bg-surface-2 px-3 py-1.5 ring-1 ring-line focus-within:ring-2 focus-within:ring-brand/60">
              <Sparkles className="size-4 shrink-0 text-brand" />
              <input ref={askBox} className="h-9 min-w-0 flex-1 bg-transparent text-sm text-strong outline-none placeholder:text-faint" value={ask} maxLength={600}
                onChange={(e) => setAsk(e.target.value)} disabled={asking} aria-label="Ask AI to change the page"
                placeholder={target ? `Describe the change to “${target.label}”…` : "Say what to change…"} />
              <button type="submit" disabled={asking || ask.trim().length < 3} aria-label="Apply"
                className="grid size-8 shrink-0 place-items-center rounded-full bg-strong text-white transition disabled:opacity-40">
                {asking ? <Loader2 className="size-4 animate-spin" /> : <ArrowUp className="size-4" />}
              </button>
            </div>
          </div>
        </form>
  );

  return createPortal(
    <div className="fixed inset-0 z-[45] flex flex-col bg-surface-2" role="region" aria-label="Page editor">
      <header className="flex flex-wrap items-center gap-2 border-b border-line bg-surface px-3 py-2 sm:px-4">
        <div className="flex min-w-0 flex-1 items-center gap-2">{left}</div>
        <div className="flex items-center gap-1">
          <span className={cx("mr-1 hidden items-center gap-1 text-xs sm:flex", status === "error" ? "text-danger" : "text-faint")} aria-live="polite">
            <StatusIcon className={cx("size-3.5", (status === "saving" || status === "dirty") && "animate-spin")} /> {statusText}
          </span>
          <button type="button" className="btn-subtle btn-sm" onClick={() => send({ type: "undo" })} disabled={!hist.undo} aria-label="Undo" title="Undo (Ctrl/⌘ Z)"><Undo2 className="size-4" /></button>
          <button type="button" className="btn-subtle btn-sm" onClick={() => send({ type: "redo" })} disabled={!hist.redo} aria-label="Redo" title="Redo (Ctrl/⌘ Shift Z)"><Redo2 className="size-4" /></button>
          <div className="inline-flex rounded-full bg-ink/[0.05] p-0.5">
            {[["desktop", Monitor], ["mobile", Smartphone]].map(([v, I]) => (
              <button key={v} type="button" onClick={() => setView(v)} aria-label={`${v} view`} aria-pressed={view === v}
                className={cx("rounded-full px-2.5 py-1.5", view === v ? "bg-surface text-strong shadow-sm" : "text-muted")}><I className="size-4" /></button>
            ))}
          </div>
          <div className="relative">
            <Button variant="ghost" size="sm" onClick={() => setDesign((d) => !d)} aria-expanded={design}><Palette className="size-4" /> <span className="hidden sm:inline">Colours</span></Button>
            {design && (
              <div className="card absolute right-0 top-11 z-10 w-72 space-y-3 p-4 text-left">
                <div className="flex items-center justify-between">
                  <p className="text-sm font-semibold text-strong">Page colours</p>
                  <button type="button" className="btn-subtle btn-sm" onClick={() => setDesign(false)} aria-label="Close"><X className="size-4" /></button>
                </div>
                {hasColors ? (
                  <>
                    <p className="text-xs text-muted">Changes every button, heading accent and highlight at once, so the page stays consistent.</p>
                    <div className="grid grid-cols-4 gap-2">
                      {PALETTES.map((p) => (
                        <button key={p.join()} type="button" onClick={() => applyPalette(p)} aria-label={`Palette ${p.join(" and ")}`}
                          className="flex h-9 overflow-hidden rounded-xl ring-1 ring-line hover:ring-2 hover:ring-brand">
                          <span className="flex-1" style={{ background: p[0] }} /><span className="w-1/3" style={{ background: p[1] }} />
                        </button>
                      ))}
                    </div>
                    <div className="flex gap-4">
                      {[[vars.main, vars.mainValue, "Main"], [vars.accent, vars.accentValue, "Accent"]].filter(([n, val]) => n && isHex(val)).map(([n, val, l]) => (
                        <label key={n} className="flex items-center gap-2 text-xs font-medium text-ink">
                          <input type="color" className="size-8 cursor-pointer rounded-full border-0 bg-transparent p-0" value={val} aria-label={`${l} colour`}
                            onChange={(e) => setColor(n, e.target.value)} /> {l}
                        </label>
                      ))}
                    </div>
                  </>
                ) : <p className="text-xs text-muted">This design doesn't use a shared colour scheme. Click a section and use Colour, or ask AI to recolour the page.</p>}
              </div>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">{right}</div>
      </header>

      <div className="flex min-h-0 flex-1">
      <div className="relative min-h-0 min-w-0 flex-1 overflow-hidden p-2 sm:p-3">
          <iframe ref={frame} title="Page editor" srcDoc={doc} sandbox="allow-scripts" 
            className={cx("mx-auto block h-full rounded-xl bg-white shadow-sm transition-all", view === "mobile" ? "w-[390px] max-w-full" : "w-full")} />
          {commenting && note && frame.current && (() => {
            const fx = frame.current.offsetLeft, fy = frame.current.offsetTop, fw = frame.current.clientWidth;
            const top = fy + note.y - scrollY;
            if (top < fy - 4 || top > fy + frame.current.clientHeight) return null;
            const flip = note.x > fw - 300;
            return (
              <div className="absolute z-10" style={{ left: fx + note.x, top }}>
                <span className={cx("absolute bottom-0 left-0 grid size-6 place-items-center rounded-[50%_50%_50%_2px] text-[11px] font-semibold text-white shadow-md ring-[1.5px] ring-white", note.busy ? "bg-strong" : "bg-brand")}>
                  {note.busy ? <Loader2 className="size-3 animate-spin" /> : 1}
                </span>
                <form onSubmit={runNote} className={cx("absolute top-2 w-72 max-w-[80vw] rounded-xl bg-surface shadow-xl ring-1 ring-ink/10", flip ? "right-1" : "left-2")}>
                  <div className="flex items-end gap-1 p-1.5">
                    <textarea autoFocus rows={1} maxLength={600} value={note.text} disabled={note.busy} placeholder={`Comment on ${note.label.length > 30 ? "this spot" : note.label}…`}
                      className="min-h-7 flex-1 resize-none bg-transparent px-1.5 py-1 text-sm leading-5 text-strong outline-none placeholder:text-muted"
                      onChange={(e) => { setNote({ ...note, text: e.target.value }); e.target.style.height = "auto"; e.target.style.height = `${Math.min(e.target.scrollHeight, 120)}px`; }}
                      onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); runNote(); } if (e.key === "Escape") setNote(null); }} />
                    <button type="submit" aria-label="Apply" disabled={note.busy || note.text.trim().length < 3}
                      className="grid size-7 shrink-0 place-items-center rounded-full bg-brand text-white disabled:bg-ink/15"><ArrowUp className="size-3.5" /></button>
                  </div>
                  {note.busy && <p className="px-3 pb-2 text-xs text-muted">Changing this part of the page…</p>}
                </form>
              </div>
            );
          })()}
        </div>
        {changes && (
          <aside aria-label="Changes" className={cx("hidden shrink-0 flex-col border-l border-line bg-surface lg:flex", panelOpen ? "w-[360px]" : "w-12")}>
            <div className={cx("flex h-11 shrink-0 items-center border-b border-line", panelOpen ? "justify-between pl-4 pr-2" : "justify-center")}>
              {panelOpen && <h2 className="text-sm font-semibold text-strong">Changes</h2>}
              <button type="button" className="btn-subtle btn-sm w-8 px-0" onClick={togglePanel} aria-expanded={panelOpen}
                aria-label={panelOpen ? "Fold the changes panel" : "Open the changes panel"} title={panelOpen ? "Fold" : "Changes"}>
                {panelOpen ? <PanelRightClose className="size-4" /> : <PanelRightOpen className="size-4" />}
              </button>
            </div>
            {panelOpen && <div className="min-h-0 flex-1 overflow-y-auto">{changes}</div>}
            {panelOpen && askForm(true)}
          </aside>
        )}
      </div>

      <div className={cx(changes && panelOpen && "lg:hidden")}>
        {changes && (
          <button type="button" className="flex w-full items-center justify-between border-t border-line bg-surface px-4 py-2 text-sm font-medium text-strong lg:hidden" onClick={() => setSheet(true)}>
            Changes <ChevronUp className="size-4 text-muted" />
          </button>
        )}
        {askForm(false)}
      </div>
      {changes && <Modal open={sheet} onClose={() => setSheet(false)} title="Changes"><div className="-mx-6">{changes}</div></Modal>}

      <Modal open={!!picking} onClose={() => setPicking(null)} title={picking?.sid ? "Add an image" : "Replace image"} wide>
        <div className="space-y-4">
          <ImageChooser value={imgRef} onChange={(v) => { setImgRef(v); setImgLink(""); }} />
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="…or an image link"><input className="input" value={imgLink} onChange={(e) => { setImgLink(e.target.value); setImgRef(""); }} placeholder="https://…" /></Field>
            <Field label="Description (alt text)" hint="Read by screen readers and Google Images.">
              <input className="input" value={picking?.alt || ""} maxLength={200} onChange={(e) => setPicking((p) => ({ ...p, alt: e.target.value }))} />
            </Field>
          </div>
          <div className="flex justify-end"><Button onClick={applyImage} disabled={!imgRef && !/^https:\/\/\S+$/.test(imgLink.trim())}>{picking?.sid ? "Add image" : "Use this image"}</Button></div>
        </div>
      </Modal>
      <Modal open={!!linking} onClose={() => setLinking(null)} title="Where should this link go?">
        <form className="space-y-4" onSubmit={(e) => {
          e.preventDefault();
          send({ type: "set-link", id: linking.id, href: linking.href.trim() });
          setLinking(null);
        }}>
          <Field label="Link" hint="A web address (https://…), #contact for the form on this page, tel:+91… or mailto:…">
            <input className="input" autoFocus value={linking?.href || ""} maxLength={500} onChange={(e) => setLinking((l) => ({ ...l, href: e.target.value }))}
              pattern="(https?://|#|tel:|mailto:|/).*" />
          </Field>
          <div className="flex justify-end"><Button type="submit">Save link</Button></div>
        </form>
      </Modal>
    </div>,
    document.body,
  );
});

export default VisualEditor;
