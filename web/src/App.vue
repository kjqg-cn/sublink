<template>
  <div id="app">
    <router-view/>
  </div>
</template>

<style lang="less">
*, *::before, *::after {
  box-sizing: border-box;
}
html, body {
  margin: 0;
  min-height: 100%;
  overflow: hidden;
}
#app{
  padding:0;
  margin:0;
}
@media (max-width: 768px) {
  html, body {
    min-height: 100%;
    overflow: auto;
  }
}
</style>
