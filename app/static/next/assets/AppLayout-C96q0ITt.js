import{d as M,i as a,j as eo,s as oo,k as to,l as Re,m as Q,n as u,p as S,S as ke,q as le,v as U,x as Be,y as ie,z as b,r as O,A as X,C as d,D as z,E as Me,F as D,G as $,H as ne,I as J,J as ro,K as Y,L as be,M as me,O as no,P as ce,Q as lo,V as io,R as Pe,T as ao,U as co,W as so,X as uo,w as F,u as B,o as te,b as L,a as G,Y as Te,B as se,t as vo,c as de,f as ho,h as ue,Z as W,_ as mo,e as fo,$ as go}from"./index-CnDPpbzu.js";import{c as po}from"./index-Dwe2Tg-1.js";import{C as bo,N as xo,a as Co,V as yo,c as ve,b as zo}from"./Dropdown-FANkzOxX.js";import{u as fe}from"./use-merged-state-v4VH5XLj.js";import{u as Io}from"./use-compitable-DRd-aVea.js";import{f as he}from"./get-B40BPwRa.js";import{N as Ne}from"./Icon-BikbjEVz.js";import{_ as So}from"./_plugin-vue_export-helper-DlAUqK2U.js";const wo=M({name:"ChevronDownFilled",render(){return a("svg",{viewBox:"0 0 16 16",fill:"none",xmlns:"http://www.w3.org/2000/svg"},a("path",{d:"M3.20041 5.73966C3.48226 5.43613 3.95681 5.41856 4.26034 5.70041L8 9.22652L11.7397 5.70041C12.0432 5.41856 12.5177 5.43613 12.7996 5.73966C13.0815 6.0432 13.0639 6.51775 12.7603 6.7996L8.51034 10.7996C8.22258 11.0668 7.77743 11.0668 7.48967 10.7996L3.23966 6.7996C2.93613 6.51775 2.91856 6.0432 3.20041 5.73966Z",fill:"currentColor"}))}});function Ro(e){const{baseColor:r,textColor2:t,bodyColor:c,cardColor:i,dividerColor:l,actionColor:h,scrollbarColor:m,scrollbarColorHover:s,invertedColor:p}=e;return{textColor:t,textColorInverted:"#FFF",color:c,colorEmbedded:h,headerColor:i,headerColorInverted:p,footerColor:h,footerColorInverted:p,headerBorderColor:l,headerBorderColorInverted:p,footerBorderColor:l,footerBorderColorInverted:p,siderBorderColor:l,siderBorderColorInverted:p,siderColor:i,siderColorInverted:p,siderToggleButtonBorder:`1px solid ${l}`,siderToggleButtonColor:r,siderToggleButtonIconColor:t,siderToggleButtonIconColorInverted:t,siderToggleBarColor:Re(c,m),siderToggleBarColorHover:Re(c,s),__invertScrollbar:"true"}}const xe=eo({name:"Layout",common:to,peers:{Scrollbar:oo},self:Ro}),Oe=Q("n-layout-sider"),Ce={type:String,default:"static"},Po=u("layout",`
 color: var(--n-text-color);
 background-color: var(--n-color);
 box-sizing: border-box;
 position: relative;
 z-index: auto;
 flex: auto;
 overflow: hidden;
 transition:
 box-shadow .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier);
`,[u("layout-scroll-container",`
 overflow-x: hidden;
 box-sizing: border-box;
 height: 100%;
 `),S("absolute-positioned",`
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 `)]),To={embedded:Boolean,position:Ce,nativeScrollbar:{type:Boolean,default:!0},scrollbarProps:Object,onScroll:Function,contentClass:String,contentStyle:{type:[String,Object],default:""},hasSider:Boolean,siderPlacement:{type:String,default:"left"}},Ee=Q("n-layout");function Le(e){return M({name:e?"LayoutContent":"Layout",props:Object.assign(Object.assign({},U.props),To),setup(r){const t=O(null),c=O(null),{mergedClsPrefixRef:i,inlineThemeDisabled:l}=le(r),h=U("Layout","-layout",Po,xe,r,i);function m(I,R){if(r.nativeScrollbar){const{value:A}=t;A&&(R===void 0?A.scrollTo(I):A.scrollTo(I,R))}else{const{value:A}=c;A&&A.scrollTo(I,R)}}X(Ee,r);let s=0,p=0;const H=I=>{var R;const A=I.target;s=A.scrollLeft,p=A.scrollTop,(R=r.onScroll)===null||R===void 0||R.call(r,I)};Be(()=>{if(r.nativeScrollbar){const I=t.value;I&&(I.scrollTop=p,I.scrollLeft=s)}});const w={display:"flex",flexWrap:"nowrap",width:"100%",flexDirection:"row"},f={scrollTo:m},_=b(()=>{const{common:{cubicBezierEaseInOut:I},self:R}=h.value;return{"--n-bezier":I,"--n-color":r.embedded?R.colorEmbedded:R.color,"--n-text-color":R.textColor}}),N=l?ie("layout",b(()=>r.embedded?"e":""),_,r):void 0;return Object.assign({mergedClsPrefix:i,scrollableElRef:t,scrollbarInstRef:c,hasSiderStyle:w,mergedTheme:h,handleNativeElScroll:H,cssVars:l?void 0:_,themeClass:N==null?void 0:N.themeClass,onRender:N==null?void 0:N.onRender},f)},render(){var r;const{mergedClsPrefix:t,hasSider:c}=this;(r=this.onRender)===null||r===void 0||r.call(this);const i=c?this.hasSiderStyle:void 0,l=[this.themeClass,e&&`${t}-layout-content`,`${t}-layout`,`${t}-layout--${this.position}-positioned`];return a("div",{class:l,style:this.cssVars},this.nativeScrollbar?a("div",{ref:"scrollableElRef",class:[`${t}-layout-scroll-container`,this.contentClass],style:[this.contentStyle,i],onScroll:this.handleNativeElScroll},this.$slots):a(ke,Object.assign({},this.scrollbarProps,{onScroll:this.onScroll,ref:"scrollbarInstRef",theme:this.mergedTheme.peers.Scrollbar,themeOverrides:this.mergedTheme.peerOverrides.Scrollbar,contentClass:this.contentClass,contentStyle:[this.contentStyle,i]}),this.$slots))}})}const Ae=Le(!1),No=Le(!0),Ao=u("layout-header",`
 transition:
 color .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 box-sizing: border-box;
 width: 100%;
 background-color: var(--n-color);
 color: var(--n-text-color);
`,[S("absolute-positioned",`
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 `),S("bordered",`
 border-bottom: solid 1px var(--n-border-color);
 `)]),_o={position:Ce,inverted:Boolean,bordered:{type:Boolean,default:!1}},Ho=M({name:"LayoutHeader",props:Object.assign(Object.assign({},U.props),_o),setup(e){const{mergedClsPrefixRef:r,inlineThemeDisabled:t}=le(e),c=U("Layout","-layout-header",Ao,xe,e,r),i=b(()=>{const{common:{cubicBezierEaseInOut:h},self:m}=c.value,s={"--n-bezier":h};return e.inverted?(s["--n-color"]=m.headerColorInverted,s["--n-text-color"]=m.textColorInverted,s["--n-border-color"]=m.headerBorderColorInverted):(s["--n-color"]=m.headerColor,s["--n-text-color"]=m.textColor,s["--n-border-color"]=m.headerBorderColor),s}),l=t?ie("layout-header",b(()=>e.inverted?"a":"b"),i,e):void 0;return{mergedClsPrefix:r,cssVars:t?void 0:i,themeClass:l==null?void 0:l.themeClass,onRender:l==null?void 0:l.onRender}},render(){var e;const{mergedClsPrefix:r}=this;return(e=this.onRender)===null||e===void 0||e.call(this),a("div",{class:[`${r}-layout-header`,this.themeClass,this.position&&`${r}-layout-header--${this.position}-positioned`,this.bordered&&`${r}-layout-header--bordered`],style:this.cssVars},this.$slots)}}),ko=u("layout-sider",`
 flex-shrink: 0;
 box-sizing: border-box;
 position: relative;
 z-index: 1;
 color: var(--n-text-color);
 transition:
 color .3s var(--n-bezier),
 border-color .3s var(--n-bezier),
 min-width .3s var(--n-bezier),
 max-width .3s var(--n-bezier),
 transform .3s var(--n-bezier),
 background-color .3s var(--n-bezier);
 background-color: var(--n-color);
 display: flex;
 justify-content: flex-end;
`,[S("bordered",[d("border",`
 content: "";
 position: absolute;
 top: 0;
 bottom: 0;
 width: 1px;
 background-color: var(--n-border-color);
 transition: background-color .3s var(--n-bezier);
 `)]),d("left-placement",[S("bordered",[d("border",`
 right: 0;
 `)])]),S("right-placement",`
 justify-content: flex-start;
 `,[S("bordered",[d("border",`
 left: 0;
 `)]),S("collapsed",[u("layout-toggle-button",[u("base-icon",`
 transform: rotate(180deg);
 `)]),u("layout-toggle-bar",[z("&:hover",[d("top",{transform:"rotate(-12deg) scale(1.15) translateY(-2px)"}),d("bottom",{transform:"rotate(12deg) scale(1.15) translateY(2px)"})])])]),u("layout-toggle-button",`
 left: 0;
 transform: translateX(-50%) translateY(-50%);
 `,[u("base-icon",`
 transform: rotate(0);
 `)]),u("layout-toggle-bar",`
 left: -28px;
 transform: rotate(180deg);
 `,[z("&:hover",[d("top",{transform:"rotate(12deg) scale(1.15) translateY(-2px)"}),d("bottom",{transform:"rotate(-12deg) scale(1.15) translateY(2px)"})])])]),S("collapsed",[u("layout-toggle-bar",[z("&:hover",[d("top",{transform:"rotate(-12deg) scale(1.15) translateY(-2px)"}),d("bottom",{transform:"rotate(12deg) scale(1.15) translateY(2px)"})])]),u("layout-toggle-button",[u("base-icon",`
 transform: rotate(0);
 `)])]),u("layout-toggle-button",`
 transition:
 color .3s var(--n-bezier),
 right .3s var(--n-bezier),
 left .3s var(--n-bezier),
 border-color .3s var(--n-bezier),
 background-color .3s var(--n-bezier);
 cursor: pointer;
 width: 24px;
 height: 24px;
 position: absolute;
 top: 50%;
 right: 0;
 border-radius: 50%;
 display: flex;
 align-items: center;
 justify-content: center;
 font-size: 18px;
 color: var(--n-toggle-button-icon-color);
 border: var(--n-toggle-button-border);
 background-color: var(--n-toggle-button-color);
 box-shadow: 0 2px 4px 0px rgba(0, 0, 0, .06);
 transform: translateX(50%) translateY(-50%);
 z-index: 1;
 `,[u("base-icon",`
 transition: transform .3s var(--n-bezier);
 transform: rotate(180deg);
 `)]),u("layout-toggle-bar",`
 cursor: pointer;
 height: 72px;
 width: 32px;
 position: absolute;
 top: calc(50% - 36px);
 right: -28px;
 `,[d("top, bottom",`
 position: absolute;
 width: 4px;
 border-radius: 2px;
 height: 38px;
 left: 14px;
 transition: 
 background-color .3s var(--n-bezier),
 transform .3s var(--n-bezier);
 `),d("bottom",`
 position: absolute;
 top: 34px;
 `),z("&:hover",[d("top",{transform:"rotate(12deg) scale(1.15) translateY(-2px)"}),d("bottom",{transform:"rotate(-12deg) scale(1.15) translateY(2px)"})]),d("top, bottom",{backgroundColor:"var(--n-toggle-bar-color)"}),z("&:hover",[d("top, bottom",{backgroundColor:"var(--n-toggle-bar-color-hover)"})])]),d("border",`
 position: absolute;
 top: 0;
 right: 0;
 bottom: 0;
 width: 1px;
 transition: background-color .3s var(--n-bezier);
 `),u("layout-sider-scroll-container",`
 flex-grow: 1;
 flex-shrink: 0;
 box-sizing: border-box;
 height: 100%;
 opacity: 0;
 transition: opacity .3s var(--n-bezier);
 max-width: 100%;
 `),S("show-content",[u("layout-sider-scroll-container",{opacity:1})]),S("absolute-positioned",`
 position: absolute;
 left: 0;
 top: 0;
 bottom: 0;
 `)]),Bo=M({props:{clsPrefix:{type:String,required:!0},onClick:Function},render(){const{clsPrefix:e}=this;return a("div",{onClick:this.onClick,class:`${e}-layout-toggle-bar`},a("div",{class:`${e}-layout-toggle-bar__top`}),a("div",{class:`${e}-layout-toggle-bar__bottom`}))}}),Mo=M({name:"LayoutToggleButton",props:{clsPrefix:{type:String,required:!0},onClick:Function},render(){const{clsPrefix:e}=this;return a("div",{class:`${e}-layout-toggle-button`,onClick:this.onClick},a(Me,{clsPrefix:e},{default:()=>a(bo,null)}))}}),Oo={position:Ce,bordered:Boolean,collapsedWidth:{type:Number,default:48},width:{type:[Number,String],default:272},contentClass:String,contentStyle:{type:[String,Object],default:""},collapseMode:{type:String,default:"transform"},collapsed:{type:Boolean,default:void 0},defaultCollapsed:Boolean,showCollapsedContent:{type:Boolean,default:!0},showTrigger:{type:[Boolean,String],default:!1},nativeScrollbar:{type:Boolean,default:!0},inverted:Boolean,scrollbarProps:Object,triggerClass:String,triggerStyle:[String,Object],collapsedTriggerClass:String,collapsedTriggerStyle:[String,Object],"onUpdate:collapsed":[Function,Array],onUpdateCollapsed:[Function,Array],onAfterEnter:Function,onAfterLeave:Function,onExpand:[Function,Array],onCollapse:[Function,Array],onScroll:Function},Eo=M({name:"LayoutSider",props:Object.assign(Object.assign({},U.props),Oo),setup(e){const r=D(Ee),t=O(null),c=O(null),i=O(e.defaultCollapsed),l=fe(ne(e,"collapsed"),i),h=b(()=>he(l.value?e.collapsedWidth:e.width)),m=b(()=>e.collapseMode!=="transform"?{}:{minWidth:he(e.width)}),s=b(()=>r?r.siderPlacement:"left");function p(T,C){if(e.nativeScrollbar){const{value:y}=t;y&&(C===void 0?y.scrollTo(T):y.scrollTo(T,C))}else{const{value:y}=c;y&&y.scrollTo(T,C)}}function H(){const{"onUpdate:collapsed":T,onUpdateCollapsed:C,onExpand:y,onCollapse:V}=e,{value:j}=l;C&&$(C,!j),T&&$(T,!j),i.value=!j,j?y&&$(y):V&&$(V)}let w=0,f=0;const _=T=>{var C;const y=T.target;w=y.scrollLeft,f=y.scrollTop,(C=e.onScroll)===null||C===void 0||C.call(e,T)};Be(()=>{if(e.nativeScrollbar){const T=t.value;T&&(T.scrollTop=f,T.scrollLeft=w)}}),X(Oe,{collapsedRef:l,collapseModeRef:ne(e,"collapseMode")});const{mergedClsPrefixRef:N,inlineThemeDisabled:I}=le(e),R=U("Layout","-layout-sider",ko,xe,e,N);function A(T){var C,y;T.propertyName==="max-width"&&(l.value?(C=e.onAfterLeave)===null||C===void 0||C.call(e):(y=e.onAfterEnter)===null||y===void 0||y.call(e))}const Z={scrollTo:p},K=b(()=>{const{common:{cubicBezierEaseInOut:T},self:C}=R.value,{siderToggleButtonColor:y,siderToggleButtonBorder:V,siderToggleBarColor:j,siderToggleBarColorHover:ae}=C,k={"--n-bezier":T,"--n-toggle-button-color":y,"--n-toggle-button-border":V,"--n-toggle-bar-color":j,"--n-toggle-bar-color-hover":ae};return e.inverted?(k["--n-color"]=C.siderColorInverted,k["--n-text-color"]=C.textColorInverted,k["--n-border-color"]=C.siderBorderColorInverted,k["--n-toggle-button-icon-color"]=C.siderToggleButtonIconColorInverted,k.__invertScrollbar=C.__invertScrollbar):(k["--n-color"]=C.siderColor,k["--n-text-color"]=C.textColor,k["--n-border-color"]=C.siderBorderColor,k["--n-toggle-button-icon-color"]=C.siderToggleButtonIconColor),k}),E=I?ie("layout-sider",b(()=>e.inverted?"a":"b"),K,e):void 0;return Object.assign({scrollableElRef:t,scrollbarInstRef:c,mergedClsPrefix:N,mergedTheme:R,styleMaxWidth:h,mergedCollapsed:l,scrollContainerStyle:m,siderPlacement:s,handleNativeElScroll:_,handleTransitionend:A,handleTriggerClick:H,inlineThemeDisabled:I,cssVars:K,themeClass:E==null?void 0:E.themeClass,onRender:E==null?void 0:E.onRender},Z)},render(){var e;const{mergedClsPrefix:r,mergedCollapsed:t,showTrigger:c}=this;return(e=this.onRender)===null||e===void 0||e.call(this),a("aside",{class:[`${r}-layout-sider`,this.themeClass,`${r}-layout-sider--${this.position}-positioned`,`${r}-layout-sider--${this.siderPlacement}-placement`,this.bordered&&`${r}-layout-sider--bordered`,t&&`${r}-layout-sider--collapsed`,(!t||this.showCollapsedContent)&&`${r}-layout-sider--show-content`],onTransitionend:this.handleTransitionend,style:[this.inlineThemeDisabled?void 0:this.cssVars,{maxWidth:this.styleMaxWidth,width:he(this.width)}]},this.nativeScrollbar?a("div",{class:[`${r}-layout-sider-scroll-container`,this.contentClass],onScroll:this.handleNativeElScroll,style:[this.scrollContainerStyle,{overflow:"auto"},this.contentStyle],ref:"scrollableElRef"},this.$slots):a(ke,Object.assign({},this.scrollbarProps,{onScroll:this.onScroll,ref:"scrollbarInstRef",style:this.scrollContainerStyle,contentStyle:this.contentStyle,contentClass:this.contentClass,theme:this.mergedTheme.peers.Scrollbar,themeOverrides:this.mergedTheme.peerOverrides.Scrollbar,builtinThemeOverrides:this.inverted&&this.cssVars.__invertScrollbar==="true"?{colorHover:"rgba(255, 255, 255, .4)",color:"rgba(255, 255, 255, .3)"}:void 0}),this.$slots),c?c==="bar"?a(Bo,{clsPrefix:r,class:t?this.collapsedTriggerClass:this.triggerClass,style:t?this.collapsedTriggerStyle:this.triggerStyle,onClick:this.handleTriggerClick}):a(Mo,{clsPrefix:r,class:t?this.collapsedTriggerClass:this.triggerClass,style:t?this.collapsedTriggerStyle:this.triggerStyle,onClick:this.handleTriggerClick}):null,this.bordered?a("div",{class:`${r}-layout-sider__border`}):null)}}),ee=Q("n-menu"),$e=Q("n-submenu"),ye=Q("n-menu-item-group"),_e=[z("&::before","background-color: var(--n-item-color-hover);"),d("arrow",`
 color: var(--n-arrow-color-hover);
 `),d("icon",`
 color: var(--n-item-icon-color-hover);
 `),u("menu-item-content-header",`
 color: var(--n-item-text-color-hover);
 `,[z("a",`
 color: var(--n-item-text-color-hover);
 `),d("extra",`
 color: var(--n-item-text-color-hover);
 `)])],He=[d("icon",`
 color: var(--n-item-icon-color-hover-horizontal);
 `),u("menu-item-content-header",`
 color: var(--n-item-text-color-hover-horizontal);
 `,[z("a",`
 color: var(--n-item-text-color-hover-horizontal);
 `),d("extra",`
 color: var(--n-item-text-color-hover-horizontal);
 `)])],Lo=z([u("menu",`
 background-color: var(--n-color);
 color: var(--n-item-text-color);
 overflow: hidden;
 transition: background-color .3s var(--n-bezier);
 box-sizing: border-box;
 font-size: var(--n-font-size);
 padding-bottom: 6px;
 `,[S("horizontal",`
 max-width: 100%;
 width: 100%;
 display: flex;
 overflow: hidden;
 padding-bottom: 0;
 `,[u("submenu","margin: 0;"),u("menu-item","margin: 0;"),u("menu-item-content",`
 padding: 0 20px;
 border-bottom: 2px solid #0000;
 `,[z("&::before","display: none;"),S("selected","border-bottom: 2px solid var(--n-border-color-horizontal)")]),u("menu-item-content",[S("selected",[d("icon","color: var(--n-item-icon-color-active-horizontal);"),u("menu-item-content-header",`
 color: var(--n-item-text-color-active-horizontal);
 `,[z("a","color: var(--n-item-text-color-active-horizontal);"),d("extra","color: var(--n-item-text-color-active-horizontal);")])]),S("child-active",`
 border-bottom: 2px solid var(--n-border-color-horizontal);
 `,[u("menu-item-content-header",`
 color: var(--n-item-text-color-child-active-horizontal);
 `,[z("a",`
 color: var(--n-item-text-color-child-active-horizontal);
 `),d("extra",`
 color: var(--n-item-text-color-child-active-horizontal);
 `)]),d("icon",`
 color: var(--n-item-icon-color-child-active-horizontal);
 `)]),J("disabled",[J("selected, child-active",[z("&:focus-within",He)]),S("selected",[q(null,[d("icon","color: var(--n-item-icon-color-active-hover-horizontal);"),u("menu-item-content-header",`
 color: var(--n-item-text-color-active-hover-horizontal);
 `,[z("a","color: var(--n-item-text-color-active-hover-horizontal);"),d("extra","color: var(--n-item-text-color-active-hover-horizontal);")])])]),S("child-active",[q(null,[d("icon","color: var(--n-item-icon-color-child-active-hover-horizontal);"),u("menu-item-content-header",`
 color: var(--n-item-text-color-child-active-hover-horizontal);
 `,[z("a","color: var(--n-item-text-color-child-active-hover-horizontal);"),d("extra","color: var(--n-item-text-color-child-active-hover-horizontal);")])])]),q("border-bottom: 2px solid var(--n-border-color-horizontal);",He)]),u("menu-item-content-header",[z("a","color: var(--n-item-text-color-horizontal);")])])]),J("responsive",[u("menu-item-content-header",`
 overflow: hidden;
 text-overflow: ellipsis;
 `)]),S("collapsed",[u("menu-item-content",[S("selected",[z("&::before",`
 background-color: var(--n-item-color-active-collapsed) !important;
 `)]),u("menu-item-content-header","opacity: 0;"),d("arrow","opacity: 0;"),d("icon","color: var(--n-item-icon-color-collapsed);")])]),u("menu-item",`
 height: var(--n-item-height);
 margin-top: 6px;
 position: relative;
 `),u("menu-item-content",`
 box-sizing: border-box;
 line-height: 1.75;
 height: 100%;
 display: grid;
 grid-template-areas: "icon content arrow";
 grid-template-columns: auto 1fr auto;
 align-items: center;
 cursor: pointer;
 position: relative;
 padding-right: 18px;
 transition:
 background-color .3s var(--n-bezier),
 padding-left .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 `,[z("> *","z-index: 1;"),z("&::before",`
 z-index: auto;
 content: "";
 background-color: #0000;
 position: absolute;
 left: 8px;
 right: 8px;
 top: 0;
 bottom: 0;
 pointer-events: none;
 border-radius: var(--n-border-radius);
 transition: background-color .3s var(--n-bezier);
 `),S("disabled",`
 opacity: .45;
 cursor: not-allowed;
 `),S("collapsed",[d("arrow","transform: rotate(0);")]),S("selected",[z("&::before","background-color: var(--n-item-color-active);"),d("arrow","color: var(--n-arrow-color-active);"),d("icon","color: var(--n-item-icon-color-active);"),u("menu-item-content-header",`
 color: var(--n-item-text-color-active);
 `,[z("a","color: var(--n-item-text-color-active);"),d("extra","color: var(--n-item-text-color-active);")])]),S("child-active",[u("menu-item-content-header",`
 color: var(--n-item-text-color-child-active);
 `,[z("a",`
 color: var(--n-item-text-color-child-active);
 `),d("extra",`
 color: var(--n-item-text-color-child-active);
 `)]),d("arrow",`
 color: var(--n-arrow-color-child-active);
 `),d("icon",`
 color: var(--n-item-icon-color-child-active);
 `)]),J("disabled",[J("selected, child-active",[z("&:focus-within",_e)]),S("selected",[q(null,[d("arrow","color: var(--n-arrow-color-active-hover);"),d("icon","color: var(--n-item-icon-color-active-hover);"),u("menu-item-content-header",`
 color: var(--n-item-text-color-active-hover);
 `,[z("a","color: var(--n-item-text-color-active-hover);"),d("extra","color: var(--n-item-text-color-active-hover);")])])]),S("child-active",[q(null,[d("arrow","color: var(--n-arrow-color-child-active-hover);"),d("icon","color: var(--n-item-icon-color-child-active-hover);"),u("menu-item-content-header",`
 color: var(--n-item-text-color-child-active-hover);
 `,[z("a","color: var(--n-item-text-color-child-active-hover);"),d("extra","color: var(--n-item-text-color-child-active-hover);")])])]),S("selected",[q(null,[z("&::before","background-color: var(--n-item-color-active-hover);")])]),q(null,_e)]),d("icon",`
 grid-area: icon;
 color: var(--n-item-icon-color);
 transition:
 color .3s var(--n-bezier),
 font-size .3s var(--n-bezier),
 margin-right .3s var(--n-bezier);
 box-sizing: content-box;
 display: inline-flex;
 align-items: center;
 justify-content: center;
 `),d("arrow",`
 grid-area: arrow;
 font-size: 16px;
 color: var(--n-arrow-color);
 transform: rotate(180deg);
 opacity: 1;
 transition:
 color .3s var(--n-bezier),
 transform 0.2s var(--n-bezier),
 opacity 0.2s var(--n-bezier);
 `),u("menu-item-content-header",`
 grid-area: content;
 transition:
 color .3s var(--n-bezier),
 opacity .3s var(--n-bezier);
 opacity: 1;
 white-space: nowrap;
 color: var(--n-item-text-color);
 `,[z("a",`
 outline: none;
 text-decoration: none;
 transition: color .3s var(--n-bezier);
 color: var(--n-item-text-color);
 `,[z("&::before",`
 content: "";
 position: absolute;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 `)]),d("extra",`
 font-size: .93em;
 color: var(--n-group-text-color);
 transition: color .3s var(--n-bezier);
 `)])]),u("submenu",`
 cursor: pointer;
 position: relative;
 margin-top: 6px;
 `,[u("menu-item-content",`
 height: var(--n-item-height);
 `),u("submenu-children",`
 overflow: hidden;
 padding: 0;
 `,[ro({duration:".2s"})])]),u("menu-item-group",[u("menu-item-group-title",`
 margin-top: 6px;
 color: var(--n-group-text-color);
 cursor: default;
 font-size: .93em;
 height: 36px;
 display: flex;
 align-items: center;
 transition:
 padding-left .3s var(--n-bezier),
 color .3s var(--n-bezier);
 `)])]),u("menu-tooltip",[z("a",`
 color: inherit;
 text-decoration: none;
 `)]),u("menu-divider",`
 transition: background-color .3s var(--n-bezier);
 background-color: var(--n-divider-color);
 height: 1px;
 margin: 6px 18px;
 `)]);function q(e,r){return[S("hover",e,r),z("&:hover",e,r)]}const Fe=M({name:"MenuOptionContent",props:{collapsed:Boolean,disabled:Boolean,title:[String,Function],icon:Function,extra:[String,Function],showArrow:Boolean,childActive:Boolean,hover:Boolean,paddingLeft:Number,selected:Boolean,maxIconSize:{type:Number,required:!0},activeIconSize:{type:Number,required:!0},iconMarginRight:{type:Number,required:!0},clsPrefix:{type:String,required:!0},onClick:Function,tmNode:{type:Object,required:!0},isEllipsisPlaceholder:Boolean},setup(e){const{props:r}=D(ee);return{menuProps:r,style:b(()=>{const{paddingLeft:t}=e;return{paddingLeft:t&&`${t}px`}}),iconStyle:b(()=>{const{maxIconSize:t,activeIconSize:c,iconMarginRight:i}=e;return{width:`${t}px`,height:`${t}px`,fontSize:`${c}px`,marginRight:`${i}px`}})}},render(){const{clsPrefix:e,tmNode:r,menuProps:{renderIcon:t,renderLabel:c,renderExtra:i,expandIcon:l}}=this,h=t?t(r.rawNode):Y(this.icon);return a("div",{onClick:m=>{var s;(s=this.onClick)===null||s===void 0||s.call(this,m)},role:"none",class:[`${e}-menu-item-content`,{[`${e}-menu-item-content--selected`]:this.selected,[`${e}-menu-item-content--collapsed`]:this.collapsed,[`${e}-menu-item-content--child-active`]:this.childActive,[`${e}-menu-item-content--disabled`]:this.disabled,[`${e}-menu-item-content--hover`]:this.hover}],style:this.style},h&&a("div",{class:`${e}-menu-item-content__icon`,style:this.iconStyle,role:"none"},[h]),a("div",{class:`${e}-menu-item-content-header`,role:"none"},this.isEllipsisPlaceholder?this.title:c?c(r.rawNode):Y(this.title),this.extra||i?a("span",{class:`${e}-menu-item-content-header__extra`}," ",i?i(r.rawNode):Y(this.extra)):null),this.showArrow?a(Me,{ariaHidden:!0,class:`${e}-menu-item-content__arrow`,clsPrefix:e},{default:()=>l?l(r.rawNode):a(wo,null)}):null)}}),re=8;function ze(e){const r=D(ee),{props:t,mergedCollapsedRef:c}=r,i=D($e,null),l=D(ye,null),h=b(()=>t.mode==="horizontal"),m=b(()=>h.value?t.dropdownPlacement:"tmNodes"in e?"right-start":"right"),s=b(()=>{var f;return Math.max((f=t.collapsedIconSize)!==null&&f!==void 0?f:t.iconSize,t.iconSize)}),p=b(()=>{var f;return!h.value&&e.root&&c.value&&(f=t.collapsedIconSize)!==null&&f!==void 0?f:t.iconSize}),H=b(()=>{if(h.value)return;const{collapsedWidth:f,indent:_,rootIndent:N}=t,{root:I,isGroup:R}=e,A=N===void 0?_:N;return I?c.value?f/2-s.value/2:A:l&&typeof l.paddingLeftRef.value=="number"?_/2+l.paddingLeftRef.value:i&&typeof i.paddingLeftRef.value=="number"?(R?_/2:_)+i.paddingLeftRef.value:0}),w=b(()=>{const{collapsedWidth:f,indent:_,rootIndent:N}=t,{value:I}=s,{root:R}=e;return h.value||!R||!c.value?re:(N===void 0?_:N)+I+re-(f+I)/2});return{dropdownPlacement:m,activeIconSize:p,maxIconSize:s,paddingLeft:H,iconMarginRight:w,NMenu:r,NSubmenu:i,NMenuOptionGroup:l}}const Ie={internalKey:{type:[String,Number],required:!0},root:Boolean,isGroup:Boolean,level:{type:Number,required:!0},title:[String,Function],extra:[String,Function]},$o=M({name:"MenuDivider",setup(){const e=D(ee),{mergedClsPrefixRef:r,isHorizontalRef:t}=e;return()=>t.value?null:a("div",{class:`${r.value}-menu-divider`})}}),je=Object.assign(Object.assign({},Ie),{tmNode:{type:Object,required:!0},disabled:Boolean,icon:Function,onClick:Function}),Fo=be(je),jo=M({name:"MenuOption",props:je,setup(e){const r=ze(e),{NSubmenu:t,NMenu:c,NMenuOptionGroup:i}=r,{props:l,mergedClsPrefixRef:h,mergedCollapsedRef:m}=c,s=t?t.mergedDisabledRef:i?i.mergedDisabledRef:{value:!1},p=b(()=>s.value||e.disabled);function H(f){const{onClick:_}=e;_&&_(f)}function w(f){p.value||(c.doSelect(e.internalKey,e.tmNode.rawNode),H(f))}return{mergedClsPrefix:h,dropdownPlacement:r.dropdownPlacement,paddingLeft:r.paddingLeft,iconMarginRight:r.iconMarginRight,maxIconSize:r.maxIconSize,activeIconSize:r.activeIconSize,mergedTheme:c.mergedThemeRef,menuProps:l,dropdownEnabled:me(()=>e.root&&m.value&&l.mode!=="horizontal"&&!p.value),selected:me(()=>c.mergedValueRef.value===e.internalKey),mergedDisabled:p,handleClick:w}},render(){const{mergedClsPrefix:e,mergedTheme:r,tmNode:t,menuProps:{renderLabel:c,nodeProps:i}}=this,l=i==null?void 0:i(t.rawNode);return a("div",Object.assign({},l,{role:"menuitem",class:[`${e}-menu-item`,l==null?void 0:l.class]}),a(xo,{theme:r.peers.Tooltip,themeOverrides:r.peerOverrides.Tooltip,trigger:"hover",placement:this.dropdownPlacement,disabled:!this.dropdownEnabled||this.title===void 0,internalExtraClass:["menu-tooltip"]},{default:()=>c?c(t.rawNode):Y(this.title),trigger:()=>a(Fe,{tmNode:t,clsPrefix:e,paddingLeft:this.paddingLeft,iconMarginRight:this.iconMarginRight,maxIconSize:this.maxIconSize,activeIconSize:this.activeIconSize,selected:this.selected,title:this.title,extra:this.extra,disabled:this.mergedDisabled,icon:this.icon,onClick:this.handleClick})}))}}),Ke=Object.assign(Object.assign({},Ie),{tmNode:{type:Object,required:!0},tmNodes:{type:Array,required:!0}}),Ko=be(Ke),Vo=M({name:"MenuOptionGroup",props:Ke,setup(e){const r=ze(e),{NSubmenu:t}=r,c=b(()=>t!=null&&t.mergedDisabledRef.value?!0:e.tmNode.disabled);X(ye,{paddingLeftRef:r.paddingLeft,mergedDisabledRef:c});const{mergedClsPrefixRef:i,props:l}=D(ee);return function(){const{value:h}=i,m=r.paddingLeft.value,{nodeProps:s}=l,p=s==null?void 0:s(e.tmNode.rawNode);return a("div",{class:`${h}-menu-item-group`,role:"group"},a("div",Object.assign({},p,{class:[`${h}-menu-item-group-title`,p==null?void 0:p.class],style:[(p==null?void 0:p.style)||"",m!==void 0?`padding-left: ${m}px;`:""]}),Y(e.title),e.extra?a(no,null," ",Y(e.extra)):null),a("div",null,e.tmNodes.map(H=>Se(H,l))))}}});function ge(e){return e.type==="divider"||e.type==="render"}function Do(e){return e.type==="divider"}function Se(e,r){const{rawNode:t}=e,{show:c}=t;if(c===!1)return null;if(ge(t))return Do(t)?a($o,Object.assign({key:e.key},t.props)):null;const{labelField:i}=r,{key:l,level:h,isGroup:m}=e,s=Object.assign(Object.assign({},t),{title:t.title||t[i],extra:t.titleExtra||t.extra,key:l,internalKey:l,level:h,root:h===0,isGroup:m});return e.children?e.isGroup?a(Vo,ce(s,Ko,{tmNode:e,tmNodes:e.children,key:l})):a(pe,ce(s,Uo,{key:l,rawNodes:t[r.childrenField],tmNodes:e.children,tmNode:e})):a(jo,ce(s,Fo,{key:l,tmNode:e}))}const Ve=Object.assign(Object.assign({},Ie),{rawNodes:{type:Array,default:()=>[]},tmNodes:{type:Array,default:()=>[]},tmNode:{type:Object,required:!0},disabled:Boolean,icon:Function,onClick:Function,domId:String,virtualChildActive:{type:Boolean,default:void 0},isEllipsisPlaceholder:Boolean}),Uo=be(Ve),pe=M({name:"Submenu",props:Ve,setup(e){const r=ze(e),{NMenu:t,NSubmenu:c}=r,{props:i,mergedCollapsedRef:l,mergedThemeRef:h}=t,m=b(()=>{const{disabled:f}=e;return c!=null&&c.mergedDisabledRef.value||i.disabled?!0:f}),s=O(!1);X($e,{paddingLeftRef:r.paddingLeft,mergedDisabledRef:m}),X(ye,null);function p(){const{onClick:f}=e;f&&f()}function H(){m.value||(l.value||t.toggleExpand(e.internalKey),p())}function w(f){s.value=f}return{menuProps:i,mergedTheme:h,doSelect:t.doSelect,inverted:t.invertedRef,isHorizontal:t.isHorizontalRef,mergedClsPrefix:t.mergedClsPrefixRef,maxIconSize:r.maxIconSize,activeIconSize:r.activeIconSize,iconMarginRight:r.iconMarginRight,dropdownPlacement:r.dropdownPlacement,dropdownShow:s,paddingLeft:r.paddingLeft,mergedDisabled:m,mergedValue:t.mergedValueRef,childActive:me(()=>{var f;return(f=e.virtualChildActive)!==null&&f!==void 0?f:t.activePathRef.value.includes(e.internalKey)}),collapsed:b(()=>i.mode==="horizontal"?!1:l.value?!0:!t.mergedExpandedKeysRef.value.includes(e.internalKey)),dropdownEnabled:b(()=>!m.value&&(i.mode==="horizontal"||l.value)),handlePopoverShowChange:w,handleClick:H}},render(){var e;const{mergedClsPrefix:r,menuProps:{renderIcon:t,renderLabel:c}}=this,i=()=>{const{isHorizontal:h,paddingLeft:m,collapsed:s,mergedDisabled:p,maxIconSize:H,activeIconSize:w,title:f,childActive:_,icon:N,handleClick:I,menuProps:{nodeProps:R},dropdownShow:A,iconMarginRight:Z,tmNode:K,mergedClsPrefix:E,isEllipsisPlaceholder:T,extra:C}=this,y=R==null?void 0:R(K.rawNode);return a("div",Object.assign({},y,{class:[`${E}-menu-item`,y==null?void 0:y.class],role:"menuitem"}),a(Fe,{tmNode:K,paddingLeft:m,collapsed:s,disabled:p,iconMarginRight:Z,maxIconSize:H,activeIconSize:w,title:f,extra:C,showArrow:!h,childActive:_,clsPrefix:E,icon:N,hover:A,onClick:I,isEllipsisPlaceholder:T}))},l=()=>a(lo,null,{default:()=>{const{tmNodes:h,collapsed:m}=this;return m?null:a("div",{class:`${r}-submenu-children`,role:"menu"},h.map(s=>Se(s,this.menuProps)))}});return this.root?a(Co,Object.assign({size:"large",trigger:"hover"},(e=this.menuProps)===null||e===void 0?void 0:e.dropdownProps,{themeOverrides:this.mergedTheme.peerOverrides.Dropdown,theme:this.mergedTheme.peers.Dropdown,builtinThemeOverrides:{fontSizeLarge:"14px",optionIconSizeLarge:"18px"},value:this.mergedValue,disabled:!this.dropdownEnabled,placement:this.dropdownPlacement,keyField:this.menuProps.keyField,labelField:this.menuProps.labelField,childrenField:this.menuProps.childrenField,onUpdateShow:this.handlePopoverShowChange,options:this.rawNodes,onSelect:this.doSelect,inverted:this.inverted,renderIcon:t,renderLabel:c}),{default:()=>a("div",{class:`${r}-submenu`,role:"menu","aria-expanded":!this.collapsed,id:this.domId},i(),this.isHorizontal?null:l())}):a("div",{class:`${r}-submenu`,role:"menu","aria-expanded":!this.collapsed,id:this.domId},i(),l())}}),Go=Object.assign(Object.assign({},U.props),{options:{type:Array,default:()=>[]},collapsed:{type:Boolean,default:void 0},collapsedWidth:{type:Number,default:48},iconSize:{type:Number,default:20},collapsedIconSize:{type:Number,default:24},rootIndent:Number,indent:{type:Number,default:32},labelField:{type:String,default:"label"},keyField:{type:String,default:"key"},childrenField:{type:String,default:"children"},disabledField:{type:String,default:"disabled"},defaultExpandAll:Boolean,defaultExpandedKeys:Array,expandedKeys:Array,value:[String,Number],defaultValue:{type:[String,Number],default:null},mode:{type:String,default:"vertical"},watchProps:{type:Array,default:void 0},disabled:Boolean,show:{type:Boolean,default:!0},inverted:Boolean,"onUpdate:expandedKeys":[Function,Array],onUpdateExpandedKeys:[Function,Array],onUpdateValue:[Function,Array],"onUpdate:value":[Function,Array],expandIcon:Function,renderIcon:Function,renderLabel:Function,renderExtra:Function,dropdownProps:Object,accordion:Boolean,nodeProps:Function,dropdownPlacement:{type:String,default:"bottom"},responsive:Boolean,items:Array,onOpenNamesChange:[Function,Array],onSelect:[Function,Array],onExpandedNamesChange:[Function,Array],expandedNames:Array,defaultExpandedNames:Array}),qo=M({name:"Menu",inheritAttrs:!1,props:Go,setup(e){const{mergedClsPrefixRef:r,inlineThemeDisabled:t}=le(e),c=U("Menu","-menu",Lo,so,e,r),i=D(Oe,null),l=b(()=>{var v;const{collapsed:x}=e;if(x!==void 0)return x;if(i){const{collapseModeRef:o,collapsedRef:g}=i;if(o.value==="width")return(v=g.value)!==null&&v!==void 0?v:!1}return!1}),h=b(()=>{const{keyField:v,childrenField:x,disabledField:o}=e;return ve(e.items||e.options,{getIgnored(g){return ge(g)},getChildren(g){return g[x]},getDisabled(g){return g[o]},getKey(g){var P;return(P=g[v])!==null&&P!==void 0?P:g.name}})}),m=b(()=>new Set(h.value.treeNodes.map(v=>v.key))),{watchProps:s}=e,p=O(null);s!=null&&s.includes("defaultValue")?Pe(()=>{p.value=e.defaultValue}):p.value=e.defaultValue;const H=ne(e,"value"),w=fe(H,p),f=O([]),_=()=>{f.value=e.defaultExpandAll?h.value.getNonLeafKeys():e.defaultExpandedNames||e.defaultExpandedKeys||h.value.getPath(w.value,{includeSelf:!1}).keyPath};s!=null&&s.includes("defaultExpandedKeys")?Pe(_):_();const N=Io(e,["expandedNames","expandedKeys"]),I=fe(N,f),R=b(()=>h.value.treeNodes),A=b(()=>h.value.getPath(w.value).keyPath);X(ee,{props:e,mergedCollapsedRef:l,mergedThemeRef:c,mergedValueRef:w,mergedExpandedKeysRef:I,activePathRef:A,mergedClsPrefixRef:r,isHorizontalRef:b(()=>e.mode==="horizontal"),invertedRef:ne(e,"inverted"),doSelect:Z,toggleExpand:E});function Z(v,x){const{"onUpdate:value":o,onUpdateValue:g,onSelect:P}=e;g&&$(g,v,x),o&&$(o,v,x),P&&$(P,v,x),p.value=v}function K(v){const{"onUpdate:expandedKeys":x,onUpdateExpandedKeys:o,onExpandedNamesChange:g,onOpenNamesChange:P}=e;x&&$(x,v),o&&$(o,v),g&&$(g,v),P&&$(P,v),f.value=v}function E(v){const x=Array.from(I.value),o=x.findIndex(g=>g===v);if(~o)x.splice(o,1);else{if(e.accordion&&m.value.has(v)){const g=x.findIndex(P=>m.value.has(P));g>-1&&x.splice(g,1)}x.push(v)}K(x)}const T=v=>{const x=h.value.getPath(v??w.value,{includeSelf:!1}).keyPath;if(!x.length)return;const o=Array.from(I.value),g=new Set([...o,...x]);e.accordion&&m.value.forEach(P=>{g.has(P)&&!x.includes(P)&&g.delete(P)}),K(Array.from(g))},C=b(()=>{const{inverted:v}=e,{common:{cubicBezierEaseInOut:x},self:o}=c.value,{borderRadius:g,borderColorHorizontal:P,fontSize:Ze,itemHeight:Je,dividerColor:Qe}=o,n={"--n-divider-color":Qe,"--n-bezier":x,"--n-font-size":Ze,"--n-border-color-horizontal":P,"--n-border-radius":g,"--n-item-height":Je};return v?(n["--n-group-text-color"]=o.groupTextColorInverted,n["--n-color"]=o.colorInverted,n["--n-item-text-color"]=o.itemTextColorInverted,n["--n-item-text-color-hover"]=o.itemTextColorHoverInverted,n["--n-item-text-color-active"]=o.itemTextColorActiveInverted,n["--n-item-text-color-child-active"]=o.itemTextColorChildActiveInverted,n["--n-item-text-color-child-active-hover"]=o.itemTextColorChildActiveInverted,n["--n-item-text-color-active-hover"]=o.itemTextColorActiveHoverInverted,n["--n-item-icon-color"]=o.itemIconColorInverted,n["--n-item-icon-color-hover"]=o.itemIconColorHoverInverted,n["--n-item-icon-color-active"]=o.itemIconColorActiveInverted,n["--n-item-icon-color-active-hover"]=o.itemIconColorActiveHoverInverted,n["--n-item-icon-color-child-active"]=o.itemIconColorChildActiveInverted,n["--n-item-icon-color-child-active-hover"]=o.itemIconColorChildActiveHoverInverted,n["--n-item-icon-color-collapsed"]=o.itemIconColorCollapsedInverted,n["--n-item-text-color-horizontal"]=o.itemTextColorHorizontalInverted,n["--n-item-text-color-hover-horizontal"]=o.itemTextColorHoverHorizontalInverted,n["--n-item-text-color-active-horizontal"]=o.itemTextColorActiveHorizontalInverted,n["--n-item-text-color-child-active-horizontal"]=o.itemTextColorChildActiveHorizontalInverted,n["--n-item-text-color-child-active-hover-horizontal"]=o.itemTextColorChildActiveHoverHorizontalInverted,n["--n-item-text-color-active-hover-horizontal"]=o.itemTextColorActiveHoverHorizontalInverted,n["--n-item-icon-color-horizontal"]=o.itemIconColorHorizontalInverted,n["--n-item-icon-color-hover-horizontal"]=o.itemIconColorHoverHorizontalInverted,n["--n-item-icon-color-active-horizontal"]=o.itemIconColorActiveHorizontalInverted,n["--n-item-icon-color-active-hover-horizontal"]=o.itemIconColorActiveHoverHorizontalInverted,n["--n-item-icon-color-child-active-horizontal"]=o.itemIconColorChildActiveHorizontalInverted,n["--n-item-icon-color-child-active-hover-horizontal"]=o.itemIconColorChildActiveHoverHorizontalInverted,n["--n-arrow-color"]=o.arrowColorInverted,n["--n-arrow-color-hover"]=o.arrowColorHoverInverted,n["--n-arrow-color-active"]=o.arrowColorActiveInverted,n["--n-arrow-color-active-hover"]=o.arrowColorActiveHoverInverted,n["--n-arrow-color-child-active"]=o.arrowColorChildActiveInverted,n["--n-arrow-color-child-active-hover"]=o.arrowColorChildActiveHoverInverted,n["--n-item-color-hover"]=o.itemColorHoverInverted,n["--n-item-color-active"]=o.itemColorActiveInverted,n["--n-item-color-active-hover"]=o.itemColorActiveHoverInverted,n["--n-item-color-active-collapsed"]=o.itemColorActiveCollapsedInverted):(n["--n-group-text-color"]=o.groupTextColor,n["--n-color"]=o.color,n["--n-item-text-color"]=o.itemTextColor,n["--n-item-text-color-hover"]=o.itemTextColorHover,n["--n-item-text-color-active"]=o.itemTextColorActive,n["--n-item-text-color-child-active"]=o.itemTextColorChildActive,n["--n-item-text-color-child-active-hover"]=o.itemTextColorChildActiveHover,n["--n-item-text-color-active-hover"]=o.itemTextColorActiveHover,n["--n-item-icon-color"]=o.itemIconColor,n["--n-item-icon-color-hover"]=o.itemIconColorHover,n["--n-item-icon-color-active"]=o.itemIconColorActive,n["--n-item-icon-color-active-hover"]=o.itemIconColorActiveHover,n["--n-item-icon-color-child-active"]=o.itemIconColorChildActive,n["--n-item-icon-color-child-active-hover"]=o.itemIconColorChildActiveHover,n["--n-item-icon-color-collapsed"]=o.itemIconColorCollapsed,n["--n-item-text-color-horizontal"]=o.itemTextColorHorizontal,n["--n-item-text-color-hover-horizontal"]=o.itemTextColorHoverHorizontal,n["--n-item-text-color-active-horizontal"]=o.itemTextColorActiveHorizontal,n["--n-item-text-color-child-active-horizontal"]=o.itemTextColorChildActiveHorizontal,n["--n-item-text-color-child-active-hover-horizontal"]=o.itemTextColorChildActiveHoverHorizontal,n["--n-item-text-color-active-hover-horizontal"]=o.itemTextColorActiveHoverHorizontal,n["--n-item-icon-color-horizontal"]=o.itemIconColorHorizontal,n["--n-item-icon-color-hover-horizontal"]=o.itemIconColorHoverHorizontal,n["--n-item-icon-color-active-horizontal"]=o.itemIconColorActiveHorizontal,n["--n-item-icon-color-active-hover-horizontal"]=o.itemIconColorActiveHoverHorizontal,n["--n-item-icon-color-child-active-horizontal"]=o.itemIconColorChildActiveHorizontal,n["--n-item-icon-color-child-active-hover-horizontal"]=o.itemIconColorChildActiveHoverHorizontal,n["--n-arrow-color"]=o.arrowColor,n["--n-arrow-color-hover"]=o.arrowColorHover,n["--n-arrow-color-active"]=o.arrowColorActive,n["--n-arrow-color-active-hover"]=o.arrowColorActiveHover,n["--n-arrow-color-child-active"]=o.arrowColorChildActive,n["--n-arrow-color-child-active-hover"]=o.arrowColorChildActiveHover,n["--n-item-color-hover"]=o.itemColorHover,n["--n-item-color-active"]=o.itemColorActive,n["--n-item-color-active-hover"]=o.itemColorActiveHover,n["--n-item-color-active-collapsed"]=o.itemColorActiveCollapsed),n}),y=t?ie("menu",b(()=>e.inverted?"a":"b"),C,e):void 0,V=ao(),j=O(null),ae=O(null);let k=!0;const we=()=>{var v;k?k=!1:(v=j.value)===null||v===void 0||v.sync({showAllItemsBeforeCalculate:!0})};function De(){return document.getElementById(V)}const oe=O(-1);function Ue(v){oe.value=e.options.length-v}function Ge(v){v||(oe.value=-1)}const qe=b(()=>{const v=oe.value;return{children:v===-1?[]:e.options.slice(v)}}),We=b(()=>{const{childrenField:v,disabledField:x,keyField:o}=e;return ve([qe.value],{getIgnored(g){return ge(g)},getChildren(g){return g[v]},getDisabled(g){return g[x]},getKey(g){var P;return(P=g[o])!==null&&P!==void 0?P:g.name}})}),Ye=b(()=>ve([{}]).treeNodes[0]);function Xe(){var v;if(oe.value===-1)return a(pe,{root:!0,level:0,key:"__ellpisisGroupPlaceholder__",internalKey:"__ellpisisGroupPlaceholder__",title:"···",tmNode:Ye.value,domId:V,isEllipsisPlaceholder:!0});const x=We.value.treeNodes[0],o=A.value,g=!!(!((v=x.children)===null||v===void 0)&&v.some(P=>o.includes(P.key)));return a(pe,{level:0,root:!0,key:"__ellpisisGroup__",internalKey:"__ellpisisGroup__",title:"···",virtualChildActive:g,tmNode:x,domId:V,rawNodes:x.rawNode.children||[],tmNodes:x.children||[],isEllipsisPlaceholder:!0})}return{mergedClsPrefix:r,controlledExpandedKeys:N,uncontrolledExpanededKeys:f,mergedExpandedKeys:I,uncontrolledValue:p,mergedValue:w,activePath:A,tmNodes:R,mergedTheme:c,mergedCollapsed:l,cssVars:t?void 0:C,themeClass:y==null?void 0:y.themeClass,overflowRef:j,counterRef:ae,updateCounter:()=>{},onResize:we,onUpdateOverflow:Ge,onUpdateCount:Ue,renderCounter:Xe,getCounter:De,onRender:y==null?void 0:y.onRender,showOption:T,deriveResponsiveState:we}},render(){const{mergedClsPrefix:e,mode:r,themeClass:t,onRender:c}=this;c==null||c();const i=()=>this.tmNodes.map(s=>Se(s,this.$props)),h=r==="horizontal"&&this.responsive,m=()=>a("div",co(this.$attrs,{role:r==="horizontal"?"menubar":"menu",class:[`${e}-menu`,t,`${e}-menu--${r}`,h&&`${e}-menu--responsive`,this.mergedCollapsed&&`${e}-menu--collapsed`],style:this.cssVars}),h?a(yo,{ref:"overflowRef",onUpdateOverflow:this.onUpdateOverflow,getCounter:this.getCounter,onUpdateCount:this.onUpdateCount,updateCounter:this.updateCounter,style:{width:"100%",display:"flex",overflow:"hidden"}},{default:i,counter:this.renderCounter}):i());return h?a(io,{onResize:this.onResize},{default:m}):m()}}),Wo={class:"top-title"},Yo={class:"top-actions"},Xo={viewBox:"0 0 24 24",width:"18",height:"18"},Zo={key:0,fill:"currentColor",d:"M12 7a5 5 0 100 10 5 5 0 000-10zM11 2v2a1 1 0 002 0V2a1 1 0 00-2 0zm0 18v2a1 1 0 002 0v-2a1 1 0 00-2 0zM2 13h2a1 1 0 000-2H2a1 1 0 000 2zm18 0h2a1 1 0 000-2h-2a1 1 0 000 2zM5.64 4.22a1 1 0 00-1.42 1.42l1.06 1.06a1 1 0 001.42-1.42L5.64 4.22zm12.02 12.02a1 1 0 00-1.42 1.42l1.06 1.06a1 1 0 001.42-1.42l-1.06-1.06zm1.06-11.6l-1.06 1.06a1 1 0 001.42 1.42l1.06-1.06a1 1 0 00-1.42-1.42zM6.34 16.24l-1.06 1.06a1 1 0 001.42 1.42l1.06-1.06a1 1 0 00-1.42-1.42z"},Jo={key:1,fill:"currentColor",d:"M12 3a9 9 0 109 9c0-.46-.04-.92-.1-1.36a5.39 5.39 0 01-4.4 2.26 5.4 5.4 0 01-3.14-9.8c-.44-.06-.9-.1-1.36-.1z"},Qo=M({__name:"AppLayout",setup(e){const r=fo(),t=go(),c=O(po());function i(H){return()=>a(Ne,null,{default:()=>a("svg",{viewBox:"0 0 24 24",width:18,height:18},[a("path",{fill:"currentColor",d:H})])})}const l={subs:"M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5",create:"M11 11V5h2v6h6v2h-6v6h-2v-6H5v-2h6z",parse:"M9.4 16.6L4.8 12l4.6-4.6L8 6l-6 6 6 6 1.4-1.4zm5.2 0l4.6-4.6-4.6-4.6L16 6l6 6-6 6-1.4-1.4z",settings:"M19.14 12.94a7.5 7.5 0 000-1.88l2.03-1.58a.5.5 0 00.12-.64l-1.92-3.32a.5.5 0 00-.6-.22l-2.39.96a7 7 0 00-1.62-.94l-.36-2.54a.5.5 0 00-.5-.42h-3.84a.5.5 0 00-.5.42l-.36 2.54c-.58.24-1.12.56-1.62.94l-2.39-.96a.5.5 0 00-.6.22L2.68 8.84a.5.5 0 00.12.64l2.03 1.58a7.5 7.5 0 000 1.88l-2.03 1.58a.5.5 0 00-.12.64l1.92 3.32a.5.5 0 00.6.22l2.39-.96c.5.38 1.04.7 1.62.94l.36 2.54a.5.5 0 00.5.42h3.84a.5.5 0 00.5-.42l.36-2.54c.58-.24 1.12-.56 1.62-.94l2.39.96a.5.5 0 00.6-.22l1.92-3.32a.5.5 0 00-.12-.64l-2.03-1.58zM12 15.5A3.5 3.5 0 1112 8.5a3.5 3.5 0 010 7z",account:"M12 12a5 5 0 100-10 5 5 0 000 10zm0 2c-4.42 0-8 2.24-8 5v1h16v-1c0-2.76-3.58-5-8-5z",logins:"M19 4h-1V2h-2v2H8V2H6v2H5a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2V6a2 2 0 00-2-2zm0 16H5V10h14v10zm0-12H5V6h14v2z"},h=[{label:()=>a(W,{to:"/subs"},{default:()=>"订阅管理"}),key:"/subs",icon:i(l.subs)},{label:()=>a(W,{to:"/subs/create"},{default:()=>"创建订阅"}),key:"/subs/create",icon:i(l.create)},{label:()=>a(W,{to:"/parse"},{default:()=>"订阅解析"}),key:"/parse",icon:i(l.parse)},{label:()=>a(W,{to:"/settings"},{default:()=>"全局设置"}),key:"/settings",icon:i(l.settings)},{label:()=>a(W,{to:"/account"},{default:()=>"账号设置"}),key:"/account",icon:i(l.account)},{label:()=>a(W,{to:"/logins"},{default:()=>"登录记录"}),key:"/logins",icon:i(l.logins)}],m=b(()=>t.path.startsWith("/subs/create")?"/subs/create":t.path.startsWith("/subs")?"/subs":t.path),s=b(()=>t.meta.title??"Sublink");function p(){localStorage.removeItem("token"),localStorage.removeItem("refresh"),r.push("/login")}return(H,w)=>{const f=mo("router-view");return te(),uo(B(Ae),{class:"shell","has-sider":""},{default:F(()=>[L(B(Eo),{bordered:"",width:230,"content-style":"display:flex;flex-direction:column;"},{default:F(()=>[w[0]||(w[0]=G("div",{class:"side-head"},[G("div",{class:"brand-logo"},"S"),G("div",null,[G("div",{class:"brand-title"},"Sublink"),G("div",{class:"brand-sub"},"订阅管理后台")])],-1)),L(B(qo),{value:m.value,options:h},null,8,["value"])]),_:1}),L(B(Ae),null,{default:F(()=>[L(B(Ho),{bordered:"",class:"top-bar"},{default:F(()=>[G("div",Wo,Te(s.value),1),G("div",Yo,[L(B(se),{quaternary:"",circle:"",onClick:B(vo)},{icon:F(()=>[L(B(Ne),null,{default:F(()=>[(te(),de("svg",Xo,[B(ho)==="light"?(te(),de("path",Zo)):(te(),de("path",Jo))]))]),_:1})]),_:1},8,["onClick"]),L(B(se),{size:"small",quaternary:"",tag:"a",href:"/"},{default:F(()=>[...w[1]||(w[1]=[ue("返回旧版",-1)])]),_:1}),L(B(zo),{bordered:!1,round:"",type:"info"},{default:F(()=>[ue(Te(c.value||"未登录"),1)]),_:1}),L(B(se),{size:"small",secondary:"",onClick:p},{default:F(()=>[...w[2]||(w[2]=[ue("退出",-1)])]),_:1})])]),_:1}),L(B(No),{class:"main"},{default:F(()=>[L(f)]),_:1})]),_:1})]),_:1})}}}),ct=So(Qo,[["__scopeId","data-v-82076ef8"]]);export{ct as default};
