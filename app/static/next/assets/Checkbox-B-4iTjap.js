import{d as j,i as d,q as H,ah as E,r as U,z as I,m as be,A as ue,H as _,G as i,D as v,n,p as $,C as T,ad as he,bc as fe,bd as ve,a4 as ke,b8 as me,af as ge,M as xe,v as G,a5 as pe,y as Ce,T as ye,F as we,c2 as ze,ab as K}from"./index-CnDPpbzu.js";import{u as V}from"./use-merged-state-v4VH5XLj.js";function Be(o,c="default",b=[]){const k=o.$slots[c];return k===void 0?b:k()}const L=be("n-checkbox-group"),Re={min:Number,max:Number,size:String,value:Array,defaultValue:{type:Array,default:null},disabled:{type:Boolean,default:void 0},"onUpdate:value":[Function,Array],onUpdateValue:[Function,Array],onChange:[Function,Array]},Fe=j({name:"CheckboxGroup",props:Re,setup(o){const{mergedClsPrefixRef:c}=H(o),b=E(o),{mergedSizeRef:C,mergedDisabledRef:k}=b,y=U(o.defaultValue),D=I(()=>o.value),u=V(D,y),M=I(()=>{var s;return((s=u.value)===null||s===void 0?void 0:s.length)||0}),a=I(()=>Array.isArray(u.value)?new Set(u.value):new Set);function w(s,r){const{nTriggerFormInput:z,nTriggerFormChange:m}=b,{onChange:l,"onUpdate:value":g,onUpdateValue:x}=o;if(Array.isArray(u.value)){const t=Array.from(u.value),F=t.findIndex(P=>P===r);s?~F||(t.push(r),x&&i(x,t,{actionType:"check",value:r}),g&&i(g,t,{actionType:"check",value:r}),z(),m(),y.value=t,l&&i(l,t)):~F&&(t.splice(F,1),x&&i(x,t,{actionType:"uncheck",value:r}),g&&i(g,t,{actionType:"uncheck",value:r}),l&&i(l,t),y.value=t,z(),m())}else s?(x&&i(x,[r],{actionType:"check",value:r}),g&&i(g,[r],{actionType:"check",value:r}),l&&i(l,[r]),y.value=[r],z(),m()):(x&&i(x,[],{actionType:"uncheck",value:r}),g&&i(g,[],{actionType:"uncheck",value:r}),l&&i(l,[]),y.value=[],z(),m())}return ue(L,{checkedCountRef:M,maxRef:_(o,"max"),minRef:_(o,"min"),valueSetRef:a,disabledRef:k,mergedSizeRef:C,toggleCheckbox:w}),{mergedClsPrefix:c}},render(){return d("div",{class:`${this.mergedClsPrefix}-checkbox-group`,role:"group"},this.$slots)}}),Se=()=>d("svg",{viewBox:"0 0 64 64",class:"check-icon"},d("path",{d:"M50.42,16.76L22.34,39.45l-8.1-11.46c-1.12-1.58-3.3-1.96-4.88-0.84c-1.58,1.12-1.95,3.3-0.84,4.88l10.26,14.51  c0.56,0.79,1.42,1.31,2.38,1.45c0.16,0.02,0.32,0.03,0.48,0.03c0.8,0,1.57-0.27,2.2-0.78l30.99-25.03c1.5-1.21,1.74-3.42,0.52-4.92  C54.13,15.78,51.93,15.55,50.42,16.76z"})),Te=()=>d("svg",{viewBox:"0 0 100 100",class:"line-icon"},d("path",{d:"M80.2,55.5H21.4c-2.8,0-5.1-2.5-5.1-5.5l0,0c0-3,2.3-5.5,5.1-5.5h58.7c2.8,0,5.1,2.5,5.1,5.5l0,0C85.2,53.1,82.9,55.5,80.2,55.5z"})),De=v([n("checkbox",`
 font-size: var(--n-font-size);
 outline: none;
 cursor: pointer;
 display: inline-flex;
 flex-wrap: nowrap;
 align-items: flex-start;
 word-break: break-word;
 line-height: var(--n-size);
 --n-merged-color-table: var(--n-color-table);
 `,[$("show-label","line-height: var(--n-label-line-height);"),v("&:hover",[n("checkbox-box",[T("border","border: var(--n-border-checked);")])]),v("&:focus:not(:active)",[n("checkbox-box",[T("border",`
 border: var(--n-border-focus);
 box-shadow: var(--n-box-shadow-focus);
 `)])]),$("inside-table",[n("checkbox-box",`
 background-color: var(--n-merged-color-table);
 `)]),$("checked",[n("checkbox-box",`
 background-color: var(--n-color-checked);
 `,[n("checkbox-icon",[v(".check-icon",`
 opacity: 1;
 transform: scale(1);
 `)])])]),$("indeterminate",[n("checkbox-box",[n("checkbox-icon",[v(".check-icon",`
 opacity: 0;
 transform: scale(.5);
 `),v(".line-icon",`
 opacity: 1;
 transform: scale(1);
 `)])])]),$("checked, indeterminate",[v("&:focus:not(:active)",[n("checkbox-box",[T("border",`
 border: var(--n-border-checked);
 box-shadow: var(--n-box-shadow-focus);
 `)])]),n("checkbox-box",`
 background-color: var(--n-color-checked);
 border-left: 0;
 border-top: 0;
 `,[T("border",{border:"var(--n-border-checked)"})])]),$("disabled",{cursor:"not-allowed"},[$("checked",[n("checkbox-box",`
 background-color: var(--n-color-disabled-checked);
 `,[T("border",{border:"var(--n-border-disabled-checked)"}),n("checkbox-icon",[v(".check-icon, .line-icon",{fill:"var(--n-check-mark-color-disabled-checked)"})])])]),n("checkbox-box",`
 background-color: var(--n-color-disabled);
 `,[T("border",`
 border: var(--n-border-disabled);
 `),n("checkbox-icon",[v(".check-icon, .line-icon",`
 fill: var(--n-check-mark-color-disabled);
 `)])]),T("label",`
 color: var(--n-text-color-disabled);
 `)]),n("checkbox-box-wrapper",`
 position: relative;
 width: var(--n-size);
 flex-shrink: 0;
 flex-grow: 0;
 user-select: none;
 -webkit-user-select: none;
 `),n("checkbox-box",`
 position: absolute;
 left: 0;
 top: 50%;
 transform: translateY(-50%);
 height: var(--n-size);
 width: var(--n-size);
 display: inline-block;
 box-sizing: border-box;
 border-radius: var(--n-border-radius);
 background-color: var(--n-color);
 transition: background-color 0.3s var(--n-bezier);
 `,[T("border",`
 transition:
 border-color .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier);
 border-radius: inherit;
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 border: var(--n-border);
 `),n("checkbox-icon",`
 display: flex;
 align-items: center;
 justify-content: center;
 position: absolute;
 left: 1px;
 right: 1px;
 top: 1px;
 bottom: 1px;
 `,[v(".check-icon, .line-icon",`
 width: 100%;
 fill: var(--n-check-mark-color);
 opacity: 0;
 transform: scale(0.5);
 transform-origin: center;
 transition:
 fill 0.3s var(--n-bezier),
 transform 0.3s var(--n-bezier),
 opacity 0.3s var(--n-bezier),
 border-color 0.3s var(--n-bezier);
 `),he({left:"1px",top:"1px"})])]),T("label",`
 color: var(--n-text-color);
 transition: color .3s var(--n-bezier);
 user-select: none;
 -webkit-user-select: none;
 padding: var(--n-label-padding);
 font-weight: var(--n-label-font-weight);
 `,[v("&:empty",{display:"none"})])]),fe(n("checkbox",`
 --n-merged-color-table: var(--n-color-table-modal);
 `)),ve(n("checkbox",`
 --n-merged-color-table: var(--n-color-table-popover);
 `))]),$e=Object.assign(Object.assign({},G.props),{size:String,checked:{type:[Boolean,String,Number],default:void 0},defaultChecked:{type:[Boolean,String,Number],default:!1},value:[String,Number],disabled:{type:Boolean,default:void 0},indeterminate:Boolean,label:String,focusable:{type:Boolean,default:!0},checkedValue:{type:[Boolean,String,Number],default:!0},uncheckedValue:{type:[Boolean,String,Number],default:!1},"onUpdate:checked":[Function,Array],onUpdateChecked:[Function,Array],privateInsideTable:Boolean,onChange:[Function,Array]}),Ie=j({name:"Checkbox",props:$e,setup(o){const c=we(L,null),b=U(null),{mergedClsPrefixRef:C,inlineThemeDisabled:k,mergedRtlRef:y,mergedComponentPropsRef:D}=H(o),u=U(o.defaultChecked),M=_(o,"checked"),a=V(M,u),w=xe(()=>{if(c){const e=c.valueSetRef.value;return e&&o.value!==void 0?e.has(o.value):!1}else return a.value===o.checkedValue}),s=E(o,{mergedSize(e){var h,f;const{size:p}=o;if(p!==void 0)return p;if(c){const{value:S}=c.mergedSizeRef;if(S!==void 0)return S}if(e){const{mergedSize:S}=e;if(S!==void 0)return S.value}const R=(f=(h=D==null?void 0:D.value)===null||h===void 0?void 0:h.Checkbox)===null||f===void 0?void 0:f.size;return R||"medium"},mergedDisabled(e){const{disabled:h}=o;if(h!==void 0)return h;if(c){if(c.disabledRef.value)return!0;const{maxRef:{value:f},checkedCountRef:p}=c;if(f!==void 0&&p.value>=f&&!w.value)return!0;const{minRef:{value:R}}=c;if(R!==void 0&&p.value<=R&&w.value)return!0}return e?e.disabled.value:!1}}),{mergedDisabledRef:r,mergedSizeRef:z}=s,m=G("Checkbox","-checkbox",De,ze,o,C);function l(e){if(c&&o.value!==void 0)c.toggleCheckbox(!w.value,o.value);else{const{onChange:h,"onUpdate:checked":f,onUpdateChecked:p}=o,{nTriggerFormInput:R,nTriggerFormChange:S}=s,B=w.value?o.uncheckedValue:o.checkedValue;f&&i(f,B,e),p&&i(p,B,e),h&&i(h,B,e),R(),S(),u.value=B}}function g(e){r.value||l(e)}function x(e){if(!r.value)switch(e.key){case" ":case"Enter":l(e)}}function t(e){switch(e.key){case" ":e.preventDefault()}}const F={focus:()=>{var e;(e=b.value)===null||e===void 0||e.focus()},blur:()=>{var e;(e=b.value)===null||e===void 0||e.blur()}},P=pe("Checkbox",y,C),N=I(()=>{const{value:e}=z,{common:{cubicBezierEaseInOut:h},self:{borderRadius:f,color:p,colorChecked:R,colorDisabled:S,colorTableHeader:B,colorTableHeaderModal:O,colorTableHeaderPopover:W,checkMarkColor:q,checkMarkColorDisabled:Y,border:J,borderFocus:Q,borderDisabled:X,borderChecked:Z,boxShadowFocus:ee,textColor:oe,textColorDisabled:re,checkMarkColorDisabledChecked:ne,colorDisabledChecked:ae,borderDisabledChecked:ce,labelPadding:le,labelLineHeight:ie,labelFontWeight:te,[K("fontSize",e)]:de,[K("size",e)]:se}}=m.value;return{"--n-label-line-height":ie,"--n-label-font-weight":te,"--n-size":se,"--n-bezier":h,"--n-border-radius":f,"--n-border":J,"--n-border-checked":Z,"--n-border-focus":Q,"--n-border-disabled":X,"--n-border-disabled-checked":ce,"--n-box-shadow-focus":ee,"--n-color":p,"--n-color-checked":R,"--n-color-table":B,"--n-color-table-modal":O,"--n-color-table-popover":W,"--n-color-disabled":S,"--n-color-disabled-checked":ae,"--n-text-color":oe,"--n-text-color-disabled":re,"--n-check-mark-color":q,"--n-check-mark-color-disabled":Y,"--n-check-mark-color-disabled-checked":ne,"--n-font-size":de,"--n-label-padding":le}}),A=k?Ce("checkbox",I(()=>z.value[0]),N,o):void 0;return Object.assign(s,F,{rtlEnabled:P,selfRef:b,mergedClsPrefix:C,mergedDisabled:r,renderedChecked:w,mergedTheme:m,labelId:ye(),handleClick:g,handleKeyUp:x,handleKeyDown:t,cssVars:k?void 0:N,themeClass:A==null?void 0:A.themeClass,onRender:A==null?void 0:A.onRender})},render(){var o;const{$slots:c,renderedChecked:b,mergedDisabled:C,indeterminate:k,privateInsideTable:y,cssVars:D,labelId:u,label:M,mergedClsPrefix:a,focusable:w,handleKeyUp:s,handleKeyDown:r,handleClick:z}=this;(o=this.onRender)===null||o===void 0||o.call(this);const m=ke(c.default,l=>M||l?d("span",{class:`${a}-checkbox__label`,id:u},M||l):null);return d("div",{ref:"selfRef",class:[`${a}-checkbox`,this.themeClass,this.rtlEnabled&&`${a}-checkbox--rtl`,b&&`${a}-checkbox--checked`,C&&`${a}-checkbox--disabled`,k&&`${a}-checkbox--indeterminate`,y&&`${a}-checkbox--inside-table`,m&&`${a}-checkbox--show-label`],tabindex:C||!w?void 0:0,role:"checkbox","aria-checked":k?"mixed":b,"aria-labelledby":u,style:D,onKeyup:s,onKeydown:r,onClick:z,onMousedown:()=>{me("selectstart",window,l=>{l.preventDefault()},{once:!0})}},d("div",{class:`${a}-checkbox-box-wrapper`}," ",d("div",{class:`${a}-checkbox-box`},d(ge,null,{default:()=>this.indeterminate?d("div",{key:"indeterminate",class:`${a}-checkbox-icon`},Te()):d("div",{key:"check",class:`${a}-checkbox-icon`},Se())}),d("div",{class:`${a}-checkbox-box__border`}))),m)}});export{Ie as N,Fe as a,Be as g};
