<script setup lang="ts">
import { useId } from 'vue'

withDefaults(defineProps<{ size?: number }>(), { size: 36 })

const uid = useId()
const bgId = `sublink-bg-${uid}`
const glossId = `sublink-gloss-${uid}`
const upperId = `sublink-upper-${uid}`
const lowerId = `sublink-lower-${uid}`
const cut1Id = `sublink-cut1-${uid}`
const cut2Id = `sublink-cut2-${uid}`
</script>

<template>
  <svg
    class="brand-logo-svg"
    xmlns="http://www.w3.org/2000/svg"
    viewBox="2 2 60 60"
    :width="size"
    :height="size"
    fill="none"
    aria-hidden="true"
  >
    <defs>
      <linearGradient :id="bgId" x1="2" y1="2" x2="62" y2="62" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stop-color="#6366f1" />
        <stop offset="55%" stop-color="#3b82f6" />
        <stop offset="100%" stop-color="#22d3ee" />
      </linearGradient>
      <linearGradient :id="glossId" x1="8" y1="2" x2="46" y2="42" gradientUnits="userSpaceOnUse">
        <stop offset="0%" stop-color="#ffffff" stop-opacity="0.16" />
        <stop offset="100%" stop-color="#ffffff" stop-opacity="0" />
      </linearGradient>
      <clipPath :id="upperId">
        <rect x="0" y="0" width="64" height="32" />
      </clipPath>
      <clipPath :id="lowerId">
        <rect x="0" y="32" width="64" height="32" />
      </clipPath>
      <mask :id="cut1Id">
        <rect x="0" y="0" width="64" height="64" fill="#ffffff" />
        <g :clip-path="`url(#${upperId})`">
          <rect x="14.61" y="25.8" width="21.2" height="12.4" rx="6.2" stroke="#000000" stroke-width="8.6" />
        </g>
      </mask>
      <mask :id="cut2Id">
        <rect x="0" y="0" width="64" height="64" fill="#ffffff" />
        <g :clip-path="`url(#${lowerId})`">
          <rect x="28.19" y="25.8" width="21.2" height="12.4" rx="6.2" stroke="#000000" stroke-width="8.6" />
        </g>
      </mask>
    </defs>
    <rect x="2" y="2" width="60" height="60" rx="16" :fill="`url(#${bgId})`" />
    <rect x="2" y="2" width="60" height="60" rx="16" :fill="`url(#${glossId})`" />
    <rect
      x="2.75"
      y="2.75"
      width="58.5"
      height="58.5"
      rx="15.25"
      stroke="#ffffff"
      stroke-opacity="0.18"
      stroke-width="1.5"
    />
    <g transform="translate(0 1.5) rotate(-45 32 32)" stroke="#1e1b4b" stroke-opacity="0.22" stroke-width="5.6">
      <rect x="14.61" y="25.8" width="21.2" height="12.4" rx="6.2" />
      <rect x="28.19" y="25.8" width="21.2" height="12.4" rx="6.2" />
    </g>
    <g transform="rotate(-45 32 32)" stroke-width="5.3">
      <rect x="14.61" y="25.8" width="21.2" height="12.4" rx="6.2" stroke="#f0f7ff" :mask="`url(#${cut2Id})`" />
      <rect x="28.19" y="25.8" width="21.2" height="12.4" rx="6.2" stroke="#ffffff" :mask="`url(#${cut1Id})`" />
    </g>
  </svg>
</template>

<style scoped>
.brand-logo-svg {
  display: block;
  flex: none;
}
</style>
