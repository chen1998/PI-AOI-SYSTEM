from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles

# from scheduled_task import ScheduledTaskManager
import logging
import os
import sys
import io

# 載入路由
from routers.common import aoi_spec_editor
from routers.defect_map_overlay import aoi_defect_map
from routers.density import aoi_density_pihour,aoi_density_defect_map
from routers.inspection import aoi_inspection, aoi_inspection_defect_map, aoi_inspection_chart_tab
from routers.capa import aoi_capa, aoi_capa_save

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')


# 統一日誌設定
logging.basicConfig(
    level=logging.DEBUG,  # 啟用 DEBUG 等級以利偵錯
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("main")

# 建立 FastAPI 應用
app = FastAPI(title="L6AN1 Project-AOI Dcfect map")

base_dir = os.path.dirname(__file__)
print(base_dir)
static_path = os.path.join(base_dir, "static")
app.mount("/static", StaticFiles(directory=static_path), name="static")

#cid_image_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'cid_images'))
#app.mount("/cid_images", StaticFiles(directory=cid_image_dir), name="cid_images")
origins = ["http://10.97.142.217:8203"]
# 設定 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # 在生產環境中應該設定具體的源
    allow_credentials=True,  # 允許攜帶憑證
    allow_methods=["*"],
    allow_headers=["*"]
)
"""
# 設定Session
app.add_middleware(
    SessionMiddleware,
    secret_key="your-secret-key",  # 請更換為安全的密鑰
    session_cookie="session"
)
"""
# 包含路由
app.include_router(aoi_defect_map.router) #, prefix="/main_page"
app.include_router(aoi_spec_editor.router)

app.include_router(aoi_inspection.router, prefix="/aoi_inspection")
app.include_router(aoi_inspection_defect_map.router, prefix="/aoi_inspection")
app.include_router(aoi_inspection_chart_tab.router, prefix="/aoi_inspection")

app.include_router(aoi_density_pihour.router, prefix="/aoi_density") #, prefix="/main_page"
app.include_router(aoi_density_defect_map.router, prefix="/aoi_density")



app.include_router(aoi_capa.router, prefix="/aoi_capa")
app.include_router(aoi_capa_save.router, prefix="/aoi_capa")


if __name__ == "__main__":
    import uvicorn
    # 啟動 FastAPI 應用
    uvicorn.run(app, host="0.0.0.0", port=8103)
