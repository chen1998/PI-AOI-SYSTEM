ROOT: AOI_Defect_map/
    #BACKEND
    main.py
    routers/
            aoi_defect_map.py
    #FRONTEND
    indx.html
    static/
        js/
        css/

網頁初始化 -> /api/run-info
前端參數
{'dates': val || '', 'line_id': val || ''}

初始資料 
AllRunInfoTableData 格式: 
{line_id:{0:{key:value in for key in cfg.run_info_table_cols },1:{}...} , line_id2:{....},...}

前端請求特定line or 特定日期區間summary-> /api/run-info
UniRunInfoTableData 格式:
{0:{key:value in for key in cfg.run_info_keys + cfg.defect_summary_keys },1:{}...}

run_info_table勾選 -> /api/defect-data
前端參數
key: f'{scantime}|{glass_id}|{recipe_id}'   (2025-09-02T08:25:45|AJ5R181Y09|803)
line_id: str

api回傳:{"defects": key_rows, "key": key}

***網頁***
                                line1 | line2 | line3...
**defect map area                                      | **run area
Defect Map（1850×1500）           原點|放大|縮小|框選放大|main-filter
                    |defect info1|sub                  |即時 Run 貨     筆數 | 
map area            |defect info2|filter area          |run table
                    |__________________________________|
                    |a img             | b img         |
_______________________________________________________|______________________________
**defect table  area                                   |**image
                                                       | AOI
defect group table1        | defect group table2       | image1       |image2
_______________________________________________________|


***問題***
在html中加入
<label class="right">
                  <input id="match-same-dot" type="checkbox" checked />
                  同點篩選(依照offset範圍內重疊)
                </label>

在defect_map中新增功能
要設置觸發match-same-dot後
在offset
