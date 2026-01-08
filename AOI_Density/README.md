ROOT: AOI_Defect_map/
    #BACKEND
    main.py
    routers/
            aoi_density.py
    #FRONTEND
    indx.html
    static/
        js/
            system_tabs.js
            aoi_density/
                api.js
                chart.js
                filter.js
                multidd.js
                router.js
                service.js
            lib/
                echarts.min.js
        css/
            aoi_density.css
            aoi_density_chart.css

前端ask /api/reset_summary_filter:
參數: dates | list
觸發情境1 初始 dates = []
        return {
                "DictData": resetData,
                "ParamDict": cfg.front_config,
        }
觸發情境2 使用者input [startdate, enddate]
        return {
                "DictData": FilterDateData,
                "ParamDict": cfg.front_config,
        }

### 前端僅有aoi density sys tab 觸發 跟 在確認DictData內資料不在使用者選擇的日期範圍內才須ask reset_summary_filter

前端filter區域非日期選擇之下拉式選單設置:
        現方法:直接在index.html寫入:
                <div id="aoiLine-dd"  class="multi-dd-host"></div>
                <div id="aoiAOI-dd"   class="multi-dd-host"></div>
                <div id="aoiModel-dd" class="multi-dd-host"></div>
                <div id="aoiSide-dd"  class="multi-dd-host"></div>
                <div id="aoiCode-dd"  class="multi-dd-host"></div>
                <div id="aoiSize-dd"  class="multi-dd-host"></div>

        用後端初始傳遞的ParamDict['filtetItemKeyDict]在js新增下拉式選單到Aoi_density-right(新增在日期下方)(現有款式Checkbox + option + 全選/清空轉換按鈕 + 選單內搜尋):
                選項使用ParamDict['filterOptionDict']對應的資料
                選單需要能在表單內搜尋字串
                點擊清空模式的按鈕時篩選方式為將DictData對應key全部不選,基本上就等於沒資料
                點擊全選的按鈕時篩選方式為將DictData對應key全選,等於對應key不做篩選全都要,僅需考慮其他選單篩選
        前端的下拉式選單都僅針對DictData進行篩選,不設置任何ask api功能
        有任意選單的選項被觸發才進行篩選,不用一直監聽
        篩選時一定根據DictData的資料格式跟邏輯避免篩選不到資料
        選單選項不需要跟著每次篩選取唯一值,一直顯示ParamDict['filterOptionDict']對應的資料選項即可,篩選純針對DictData進行,篩選後的資料用於清理成chartdata後製圖顯示
        

前端chart:
        1.初始: 使用DictData製圖顯示
        2.filter: 觸發filter option時根據filter後取得的資料重新製圖顯示
        ### 目前chart顯示問題: pi hour軸僅需一個固定在chart下方,不然每個line都有一個的話會一直遮擋到下方的其他line資料
        懸浮框要顯示line,aol,model所有對應資料
