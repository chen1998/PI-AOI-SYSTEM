
  
  
document.addEventListener("aoi_density:subtab-chart", (ev)=>{
    const { tabKey, config } = ev.detail || {};
    console.log("chart subtab switched:", tabKey, config);
  
    // 這裡用 config + AOI.state.rows 做月/週/日 trend 圖
});