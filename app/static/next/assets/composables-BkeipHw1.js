import{n as e,D as t,C as u,d as v,i as m,q as z,aE as S,v as x,ah as B,y as G,z as h,aF as L,ab as f,aG as _,F as $,aH as k}from"./index-CnDPpbzu.js";const j=e("input-group",`
 display: inline-flex;
 width: 100%;
 flex-wrap: nowrap;
 vertical-align: bottom;
`,[t(">",[e("input",[t("&:not(:last-child)",`
 border-top-right-radius: 0!important;
 border-bottom-right-radius: 0!important;
 `),t("&:not(:first-child)",`
 border-top-left-radius: 0!important;
 border-bottom-left-radius: 0!important;
 margin-left: -1px!important;
 `)]),e("button",[t("&:not(:last-child)",`
 border-top-right-radius: 0!important;
 border-bottom-right-radius: 0!important;
 `,[u("state-border, border",`
 border-top-right-radius: 0!important;
 border-bottom-right-radius: 0!important;
 `)]),t("&:not(:first-child)",`
 border-top-left-radius: 0!important;
 border-bottom-left-radius: 0!important;
 `,[u("state-border, border",`
 border-top-left-radius: 0!important;
 border-bottom-left-radius: 0!important;
 `)])]),t("*",[t("&:not(:last-child)",`
 border-top-right-radius: 0!important;
 border-bottom-right-radius: 0!important;
 `,[t(">",[e("input",`
 border-top-right-radius: 0!important;
 border-bottom-right-radius: 0!important;
 `),e("base-selection",[e("base-selection-label",`
 border-top-right-radius: 0!important;
 border-bottom-right-radius: 0!important;
 `),e("base-selection-tags",`
 border-top-right-radius: 0!important;
 border-bottom-right-radius: 0!important;
 `),u("box-shadow, border, state-border",`
 border-top-right-radius: 0!important;
 border-bottom-right-radius: 0!important;
 `)])])]),t("&:not(:first-child)",`
 margin-left: -1px!important;
 border-top-left-radius: 0!important;
 border-bottom-left-radius: 0!important;
 `,[t(">",[e("input",`
 border-top-left-radius: 0!important;
 border-bottom-left-radius: 0!important;
 `),e("base-selection",[e("base-selection-label",`
 border-top-left-radius: 0!important;
 border-bottom-left-radius: 0!important;
 `),e("base-selection-tags",`
 border-top-left-radius: 0!important;
 border-bottom-left-radius: 0!important;
 `),u("box-shadow, border, state-border",`
 border-top-left-radius: 0!important;
 border-bottom-left-radius: 0!important;
 `)])])])])])]),E={},N=v({name:"InputGroup",props:E,setup(r){const{mergedClsPrefixRef:o}=z(r);return S("-input-group",j,o),{mergedClsPrefix:o}},render(){const{mergedClsPrefix:r}=this;return m("div",{class:`${r}-input-group`},this.$slots)}}),T=e("input-group-label",`
 position: relative;
 user-select: none;
 -webkit-user-select: none;
 box-sizing: border-box;
 padding: 0 12px;
 display: inline-block;
 border-radius: var(--n-border-radius);
 background-color: var(--n-group-label-color);
 color: var(--n-group-label-text-color);
 font-size: var(--n-font-size);
 line-height: var(--n-height);
 height: var(--n-height);
 flex-shrink: 0;
 white-space: nowrap;
 transition: 
 color .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier);
`,[u("border",`
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 border-radius: inherit;
 border: var(--n-group-label-border);
 transition: border-color .3s var(--n-bezier);
 `)]),D=Object.assign(Object.assign({},x.props),{size:String,bordered:{type:Boolean,default:void 0}}),O=v({name:"InputGroupLabel",props:D,setup(r){const{mergedBorderedRef:o,mergedClsPrefixRef:i,inlineThemeDisabled:n,mergedComponentPropsRef:p}=z(r),C=x("Input","-input-group-label",T,L,r,i),{mergedSizeRef:g}=B(r,{mergedSize(s){var d,l;if(r.size!==void 0)return r.size;if(s)return s.mergedSize.value;const b=(l=(d=p==null?void 0:p.value)===null||d===void 0?void 0:d.Input)===null||l===void 0?void 0:l.size;return b||"medium"}}),c=h(()=>{const{value:s}=g,{common:{cubicBezierEaseInOut:d},self:{groupLabelColor:l,borderRadius:b,groupLabelTextColor:R,lineHeight:w,groupLabelBorder:y,[f("fontSize",s)]:P,[f("height",s)]:I}}=C.value;return{"--n-bezier":d,"--n-group-label-color":l,"--n-group-label-border":y,"--n-border-radius":b,"--n-group-label-text-color":R,"--n-font-size":P,"--n-line-height":w,"--n-height":I}}),a=n?G("input-group-label",h(()=>g.value[0]),c,r):void 0;return{mergedClsPrefix:i,mergedBordered:o,cssVars:n?void 0:c,themeClass:a==null?void 0:a.themeClass,onRender:a==null?void 0:a.onRender}},render(){var r,o,i;const{mergedClsPrefix:n}=this;return(r=this.onRender)===null||r===void 0||r.call(this),m("div",{class:[`${n}-input-group-label`,this.themeClass],style:this.cssVars},(i=(o=this.$slots).default)===null||i===void 0?void 0:i.call(o),this.mergedBordered?m("div",{class:`${n}-input-group-label__border`}):null)}});function V(){const r=$(k,null);return r===null&&_("use-dialog","No outer <n-dialog-provider /> founded."),r}export{O as N,N as a,V as u};
