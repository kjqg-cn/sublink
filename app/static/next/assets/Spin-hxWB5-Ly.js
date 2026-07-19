import{av as G,aw as I,d as P,ax as N,i as p,ay as V,q as O,v as S,a5 as W,z as y,ab as k,az as D,aj as B,D as j,n as v,aA as L,p as T,ag as M,aB as _,y as A,R as H,r as F,aC as K,aD as U,ai as q}from"./index-CnDPpbzu.js";import{g as J}from"./Checkbox-B-4iTjap.js";import{u as X}from"./use-compitable-DRd-aVea.js";function Y(){return G}const Q={self:Y};let $;function Z(){if(!I)return!0;if($===void 0){const e=document.createElement("div");e.style.display="flex",e.style.flexDirection="column",e.style.rowGap="1px",e.appendChild(document.createElement("div")),e.appendChild(document.createElement("div")),document.body.appendChild(e);const a=e.scrollHeight===1;return document.body.removeChild(e),$=a}return $}const ee=Object.assign(Object.assign({},S.props),{align:String,justify:{type:String,default:"start"},inline:Boolean,vertical:Boolean,reverse:Boolean,size:[String,Number,Array],wrapItem:{type:Boolean,default:!0},itemClass:String,itemStyle:[String,Object],wrap:{type:Boolean,default:!0},internalUseGap:{type:Boolean,default:void 0}}),oe=P({name:"Space",props:ee,setup(e){const{mergedClsPrefixRef:a,mergedRtlRef:i,mergedComponentPropsRef:s}=O(e),r=y(()=>{var t,n;return e.size||((n=(t=s==null?void 0:s.value)===null||t===void 0?void 0:t.Space)===null||n===void 0?void 0:n.size)||"medium"}),o=S("Space","-space",void 0,Q,e,a),d=W("Space",i,a);return{useGap:Z(),rtlEnabled:d,mergedClsPrefix:a,margin:y(()=>{const t=r.value;if(Array.isArray(t))return{horizontal:t[0],vertical:t[1]};if(typeof t=="number")return{horizontal:t,vertical:t};const{self:{[k("gap",t)]:n}}=o.value,{row:l,col:c}=D(n);return{horizontal:B(c),vertical:B(l)}})}},render(){const{vertical:e,reverse:a,align:i,inline:s,justify:r,itemClass:o,itemStyle:d,margin:t,wrap:n,mergedClsPrefix:l,rtlEnabled:c,useGap:u,wrapItem:x,internalUseGap:C}=this,f=N(J(this),!1);if(!f.length)return null;const R=`${t.horizontal}px`,b=`${t.horizontal/2}px`,E=`${t.vertical}px`,g=`${t.vertical/2}px`,h=f.length-1,z=r.startsWith("space-");return p("div",{role:"none",class:[`${l}-space`,c&&`${l}-space--rtl`],style:{display:s?"inline-flex":"flex",flexDirection:e&&!a?"column":e&&a?"column-reverse":!e&&a?"row-reverse":"row",justifyContent:["start","end"].includes(r)?`flex-${r}`:r,flexWrap:!n||e?"nowrap":"wrap",marginTop:u||e?"":`-${g}`,marginBottom:u||e?"":`-${g}`,alignItems:i,gap:u?`${t.vertical}px ${t.horizontal}px`:""}},!x&&(u||C)?f:f.map((w,m)=>w.type===V?w:p("div",{role:"none",class:o,style:[d,{maxWidth:"100%"},u?"":e?{marginBottom:m!==h?E:""}:c?{marginLeft:z?r==="space-between"&&m===h?"":b:m!==h?R:"",marginRight:z?r==="space-between"&&m===0?"":b:"",paddingTop:g,paddingBottom:g}:{marginRight:z?r==="space-between"&&m===h?"":b:m!==h?R:"",marginLeft:z?r==="space-between"&&m===0?"":b:"",paddingTop:g,paddingBottom:g}]},w)))}}),te=j([j("@keyframes spin-rotate",`
 from {
 transform: rotate(0);
 }
 to {
 transform: rotate(360deg);
 }
 `),v("spin-container",`
 position: relative;
 `,[v("spin-body",`
 position: absolute;
 top: 50%;
 left: 50%;
 transform: translateX(-50%) translateY(-50%);
 `,[L()])]),v("spin-body",`
 display: inline-flex;
 align-items: center;
 justify-content: center;
 flex-direction: column;
 `),v("spin",`
 display: inline-flex;
 height: var(--n-size);
 width: var(--n-size);
 font-size: var(--n-size);
 color: var(--n-color);
 `,[T("rotate",`
 animation: spin-rotate 2s linear infinite;
 `)]),v("spin-description",`
 display: inline-block;
 font-size: var(--n-font-size);
 color: var(--n-text-color);
 transition: color .3s var(--n-bezier);
 margin-top: 8px;
 `),v("spin-content",`
 opacity: 1;
 transition: opacity .3s var(--n-bezier);
 pointer-events: all;
 `,[T("spinning",`
 user-select: none;
 -webkit-user-select: none;
 pointer-events: none;
 opacity: var(--n-opacity-spinning);
 `)])]),ne={small:20,medium:18,large:16},se=Object.assign(Object.assign(Object.assign({},S.props),{contentClass:String,contentStyle:[Object,String],description:String,size:{type:[String,Number],default:"medium"},show:{type:Boolean,default:!0},rotate:{type:Boolean,default:!0},spinning:{type:Boolean,validator:()=>!0,default:void 0},delay:Number}),K),le=P({name:"Spin",props:se,slots:Object,setup(e){const{mergedClsPrefixRef:a,inlineThemeDisabled:i}=O(e),s=S("Spin","-spin",te,U,e,a),r=y(()=>{const{size:n}=e,{common:{cubicBezierEaseInOut:l},self:c}=s.value,{opacitySpinning:u,color:x,textColor:C}=c,f=typeof n=="number"?q(n):c[k("size",n)];return{"--n-bezier":l,"--n-opacity-spinning":u,"--n-size":f,"--n-color":x,"--n-text-color":C}}),o=i?A("spin",y(()=>{const{size:n}=e;return typeof n=="number"?String(n):n[0]}),r,e):void 0,d=X(e,["spinning","show"]),t=F(!1);return H(n=>{let l;if(d.value){const{delay:c}=e;if(c){l=window.setTimeout(()=>{t.value=!0},c),n(()=>{clearTimeout(l)});return}}t.value=d.value}),{mergedClsPrefix:a,active:t,mergedStrokeWidth:y(()=>{const{strokeWidth:n}=e;if(n!==void 0)return n;const{size:l}=e;return ne[typeof l=="number"?"medium":l]}),cssVars:i?void 0:r,themeClass:o==null?void 0:o.themeClass,onRender:o==null?void 0:o.onRender}},render(){var e,a;const{$slots:i,mergedClsPrefix:s,description:r}=this,o=i.icon&&this.rotate,d=(r||i.description)&&p("div",{class:`${s}-spin-description`},r||((e=i.description)===null||e===void 0?void 0:e.call(i))),t=i.icon?p("div",{class:[`${s}-spin-body`,this.themeClass]},p("div",{class:[`${s}-spin`,o&&`${s}-spin--rotate`],style:i.default?"":this.cssVars},i.icon()),d):p("div",{class:[`${s}-spin-body`,this.themeClass]},p(M,{clsPrefix:s,style:i.default?"":this.cssVars,stroke:this.stroke,"stroke-width":this.mergedStrokeWidth,radius:this.radius,scale:this.scale,class:`${s}-spin`}),d);return(a=this.onRender)===null||a===void 0||a.call(this),i.default?p("div",{class:[`${s}-spin-container`,this.themeClass],style:this.cssVars},p("div",{class:[`${s}-spin-content`,this.active&&`${s}-spin-content--spinning`,this.contentClass],style:this.contentStyle},i),p(_,{name:"fade-in-transition"},{default:()=>this.active?t:null})):t}});export{oe as N,le as a};
