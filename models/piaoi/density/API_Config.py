# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Tuple
import sys
import pandas as pd

sys.path.insert(0, r"D:/A0_Project")
from models.piaoi.density.cim_density_job import Config as DensityJobConfig


@dataclass
class API_Config:
    """
    Density Router API side config.

    三層 Density 主資料表：

    1) density_tab_summary_yyyymm
       grain:
         line_id + aoi + model + glass_type + pi_hour + tab_name

       用途:
         Chart 固定母體 total。
         不受 recipe_id / adc_def_code / defect_size filter 影響。

    2) density_recipe_summary_yyyymm
       grain:
         line_id + aoi + model + glass_type + pi_hour + recipe_id

       用途:
         recipe 母體資訊。

    3) density_code_summary_yyyymm
       grain:
         line_id + aoi + model + glass_type + pi_hour + recipe_id + adc_def_code

       用途:
         defect code 明細、filter、點 bar 展開、glass_size_detail。

    新增 Same Point 資料表：

    4) density_recipe_same_point_yyyymm
       grain:
         line_id + aoi + model + glass_type + pi_hour + recipe_id + offset

       用途:
         UPI(Total) / PISpot(Total) 分頁的 recipe 母體同點分析。
    """

    density_cfg: DensityJobConfig = field(default_factory=DensityJobConfig)

    # runtime
    now: datetime = field(default_factory=datetime.now)

    # fixed sets
    uni_aoi_names: List[str] = field(default_factory=lambda: [f"aoi{i}00" for i in range(1, 4)])
    uni_pi_names: List[str] = field(default_factory=lambda: [f"pi{i}00" for i in range(1, 8)])

    uni_UPI_defect_codes: List[str] = field(default_factory=lambda: [
        "Polymer",
        "SSIU_Polymer",
        "NPI_TFT",
    ])

    uni_SPOT_defect_codes: List[str] = field(default_factory=lambda: [
        "PI_Spot_NP",
        "PIS With Particle",
        "NPI_TFT",
    ])

    uni_SPS_defect_codes: List[str] = field(default_factory=lambda: ["SPS"])

    uni_defect_types: List[str] = field(default_factory=lambda: ["Particle", "PISpot"])

    all_defect_codes: List[str] = field(default_factory=lambda: [
        "Polymer",
        "SSIU_Polymer",
        "PI_Spot_NP",
        "PIS With Particle",
        "SPS",
        "NPI_TFT",
        "others",
    ])

    # defect size config
    uni_defect_sizes: List[str] = field(default_factory=lambda: ["S", "M", "L", "O"])
    rawdata_defect_size_col: str = "defect_size"

    size_group_keys: List[str] = field(default_factory=lambda: [
        "S", "SM", "O", "OL",
        "SML", "OLM", "SMLO",
    ])

    # Glass side
    glass_sides: List[str] = field(default_factory=lambda: ["CF", "TFT"])

    # -------------------------------------------------------------------------
    # DB table names
    # -------------------------------------------------------------------------
    aoi_density_tab_tbn: str = ""
    aoi_density_recipe_tbn: str = ""
    aoi_density_code_tbn: str = ""
    aoi_density_same_point_tbn: str = ""

    # 舊名稱相容
    aoi_density_summary_tbn: str = ""
    aoi_pidensit_summary_tbn: str = ""
    aoi_pi_density_tbns: List[str] = field(default_factory=list)

    # -------------------------------------------------------------------------
    # SQL / API column specs
    # -------------------------------------------------------------------------
    aoi_density_tab_sql_cols: List[str] = field(default_factory=list)
    aoi_density_recipe_sql_cols: List[str] = field(default_factory=list)
    aoi_density_code_sql_cols: List[str] = field(default_factory=list)

    # Same Point table columns
    aoi_density_same_point_sql_cols: List[str] = field(default_factory=list)
    aoi_density_same_point_api_cols: List[str] = field(default_factory=list)

    # 舊名稱相容：目前主 DictData 仍以 code summary 為主
    aoi_density_summary_sql_cols: List[str] = field(default_factory=list)
    aoi_density_summary_api_cols: List[str] = field(default_factory=list)

    aoi_density_rawdata_sql_cols: List[str] = field(default_factory=lambda: [
        "sheet_id_chip_id",
        "chip_id",
        "test_time",
        "defect_size",
        "pox_x1",
        "pox_y1",
        "image_file_path",
        "image_file_name",
        "retype_def_code",
        "adc_def_code",
        "pi_time",
        "pi_hour",
    ])

    # 前端 chart 的固定母體層級
    PRIMARY_GROUP_COLS: List[str] = field(default_factory=lambda: [
        "pi_hour",
        "line_id",
        "aoi",
        "model",
        "glass_type",
    ])

    # -------------------------------------------------------------------------
    # Same Point config
    # -------------------------------------------------------------------------
    same_point_offsets: List[int] = field(default_factory=lambda: list(range(20, 101, 10)))
    same_point_default_offset: int = 20
    same_point_enabled_tabs: List[str] = field(default_factory=lambda: [
        "UPI(Total)","PISpot(Total)",
    ])

    # -------------------------------------------------------------------------
    # spec tables
    # -------------------------------------------------------------------------
    default_spec_table_name: str = "default_spec_table"
    fixed_spec_table_name: str = "fix_spec_table"

    default_spec_table_cols: List[str] = field(default_factory=lambda: [
        "line_id",
        "model",
        "glass_type",
        "adc_def_code",
        "defect_size",
        "OOC",
        "OOS",
        "Editor",
        "modify_time",
        "drop",
        "MODEL_TYPE",
        "PROCESS_TYPE",
    ])

    fixed_spec_table_cols: List[str] = field(default_factory=lambda: [
        "line_id",
        "aoi",
        "model",
        "recipe_id",
        "glass_type",
        "adc_def_code",
        "defect_size",
        "total_glass_cnt",
        "defect_cnt",
        "density",
        "overD",
        "removed_glasses",
        "removed_defects",
        "final_glass_cnt",
        "final_defect_cnt",
        "final_density",
        "std",
        "OOC",
        "OOS",
        "GEN_DT",
        "PERIOD_START",
        "PERIOD_END",
        "DAYS",
    ])

    default_spec_coldict: Dict[str, str] = field(default_factory=lambda: {
        "line_id": "PI Line",
        "model": "MODEL_ID",
        "MODEL_TYPE": "MODEL_TYPE",
        "glass_type": "GLASS_TYPE",
        "adc_def_code": "DEFECT_CODE",
        "defect_size": "SIZE_TYPE",
        "OOC": "OOC",
        "OOS": "OOS",
        "Editor": "Editor",
        "modify_time": "modify_time",
    })

    # -------------------------------------------------------------------------
    # front-end config dicts
    # -------------------------------------------------------------------------
    chart_table_coldict: Dict[str, str] = field(default_factory=dict)
    table_group_key_dict: Dict[str, List[str]] = field(default_factory=dict)
    chart_group_dict: Dict[str, List[str]] = field(default_factory=dict)
    uni_glass_row_info_dict: Dict[str, str] = field(default_factory=dict)
    defect_group_coldict: Dict[str, str] = field(default_factory=dict)
    filter_item_coldict: Dict[str, str] = field(default_factory=dict)
    tab_filter_config: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    same_point_table_coldict: Dict[str, str] = field(default_factory=dict)
    same_point_table_group_key_dict: Dict[str, List[str]] = field(default_factory=dict)
    same_point_filter_item_coldict: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    front_config: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    target_defect_codes: Tuple[str, ...] = field(default_factory=lambda: (
        "Polymer",
        "SSIU_Polymer",
        "PI_Spot_NP",
        "PIS With Particle",
        "SPS",
        "NPI_TFT",
        "others",
    ))

    def __post_init__(self) -> None:
        ym = self.now.strftime("%Y%m")

        self.aoi_density_tab_tbn = f"density_tab_summary_{ym}"
        self.aoi_density_recipe_tbn = f"density_recipe_summary_{ym}"
        self.aoi_density_code_tbn = f"density_code_summary_{ym}"
        self.aoi_density_same_point_tbn = f"density_recipe_same_point_{ym}"

        # 舊名稱相容
        self.aoi_density_summary_tbn = self.aoi_density_code_tbn
        self.aoi_pidensit_summary_tbn = self.aoi_density_code_tbn

        self.aoi_pi_density_tbns = [
            self.aoi_density_tab_tbn,
            self.aoi_density_recipe_tbn,
            self.aoi_density_code_tbn,
            self.aoi_density_same_point_tbn,
        ]

        self.target_defect_codes = tuple(getattr(self.density_cfg, "target_defect_codes", ()))
        self.all_defect_codes = list(self.target_defect_codes)

        # =========================================================
        # 1) density_tab_summary_yyyymm 欄位
        # =========================================================
        self.aoi_density_tab_sql_cols = [
            "line_id",
            "aoi",
            "model",
            "glass_type",
            "pi_hour",

            "recipe_family",
            "tab_name",

            "tab_total_glass_cnt",
            "tab_total_defect_cnt",
            "tab_total_density",

            "tab_raw_defect_cnt",
            "tab_total_defect_gap",

            "recipe_list",
            "glass",
        ]

        # =========================================================
        # 2) density_recipe_summary_yyyymm 欄位
        # =========================================================
        self.aoi_density_recipe_sql_cols = [
            "line_id",
            "aoi",
            "model",
            "glass_type",
            "pi_hour",
            "recipe_id",

            "recipe_total_glass_cnt",
            "recipe_total_defect_cnt",
            "recipe_total_density",

            "recipe_raw_defect_cnt",
            "recipe_total_defect_gap",

            "glass",
        ]

        # =========================================================
        # 3) density_code_summary_yyyymm 欄位
        # =========================================================
        self.aoi_density_code_sql_cols = [
            "line_id",
            "aoi",
            "model",
            "glass_type",
            "pi_hour",
            "recipe_id",
            "adc_def_code",

            "recipe_total_glass_cnt",
            "recipe_total_defect_cnt",
            "recipe_total_density",

            "recipe_raw_defect_cnt",
            "recipe_total_defect_gap",

            "defect_cnt",
            "def_glass_cnt",
            "glass_cnt",
            "recipe_code_density",
            "density",

            "small_defect_count",
            "middle_defect_count",
            "large_defect_count",
            "over_defect_count",

            "glass",
            "glass_size_detail",

            "comment",
            "action",
            "Editor",
            "modify_time",
        ]

        # =========================================================
        # 4) density_recipe_same_point_yyyymm 欄位
        #
        # grain:
        #   line_id + aoi + model + glass_type + pi_hour + recipe_id + offset
        #
        # common_cnt:
        #   同點 pair 數量。
        #
        # common_glass_cnt:
        #   有同點 pair 的 glass 數量。
        #
        # common_points_details:
        #   JSON。
        #   建議格式：
        #   [
        #     {
        #       "glass_id": "...",
        #       "test_time": "...",
        #       "offset": 20,
        #       "point_rank": 1,
        #       "distance": 12.3,
        #       "dx": 1.1,
        #       "dy": -2.2,
        #       "defect_a": {
        #         "x": 123,
        #         "y": 456,
        #         "defect_size": "S",
        #         "defect_code": "Polymer",
        #         "img_url": "..."
        #       },
        #       "defect_b": {
        #         "x": 125,
        #         "y": 458,
        #         "defect_size": "M",
        #         "defect_code": "SSIU_Polymer",
        #         "img_url": "..."
        #       }
        #     }
        #   ]
        # =========================================================
        self.aoi_density_same_point_sql_cols = [
            "line_id",
            "aoi",
            "model",
            "glass_type",
            "pi_hour",
            "recipe_id",
            "offset",

            "common_cnt",
            "common_glass_cnt",
            "common_points_details",

            "gen_time",
        ]

        self.aoi_density_same_point_api_cols = self.aoi_density_same_point_sql_cols[:]

        # 舊名稱相容：主 DictData 仍回傳 code summary
        self.aoi_density_summary_sql_cols = self.aoi_density_code_sql_cols[:]

        self.aoi_density_summary_api_cols = [
            "line_id",
            "aoi",
            "model",
            "glass_type",
            "pi_hour",
            "recipe_id",
            "adc_def_code",

            "recipe_total_glass_cnt",
            "recipe_total_defect_cnt",
            "recipe_total_density",

            "recipe_raw_defect_cnt",
            "recipe_total_defect_gap",

            "defect_cnt",
            "def_glass_cnt",
            "glass_cnt",
            "recipe_code_density",
            "density",

            "small_defect_count",
            "middle_defect_count",
            "large_defect_count",
            "over_defect_count",
            "size_mask",

            "glass",
            "glass_size_detail",

            "comment",
            "action",
            "Editor",
            "modify_time",
        ]

        # =========================================================
        # Front-end table display config
        #
        # Chart 固定母體 total 由 TabSummaryData / TabTotalDict 提供。
        # DictData 本身是 recipe + adc_def_code 明細。
        # =========================================================
        self.chart_table_coldict = {
            "line_id": "PI Line",
            "aoi": "aoi",
            "model": "Model",
            "glass_type": "side",
            "pi_hour": "Hourly",

            # chart 母體欄位：來源是 TabSummaryData / TabTotalDict
            "tab_total_glass_cnt": "total gld",
            "tab_total_defect_cnt": "total defect",
            "tab_total_density": "total density",

            # recipe/code 明細欄位
            "recipe_id": "recipe",
            "adc_def_code": "defect",
            "def_glass_cnt": "def gld",
            "defect_cnt": "def cnt",

            "glass": "glass",
            "glass_size_detail": "size",
        }

        self.table_group_key_dict = {
            # 明細 row 的主鍵必須包含 recipe_id + adc_def_code
            "main_group": [
                "pi_hour",
                "line_id",
                "aoi",
                "model",
                "glass_type",
                "tab_total_glass_cnt",
                "tab_total_defect_cnt",
                "tab_total_density",

                "recipe_id",

                "adc_def_code",
                "defect_cnt",
                "def_glass_cnt",

                "comment",
                "action",
                "Editor",
                "modify_time",
            ],
            "uni_col": [
                "glass",
                "glass_size_detail",
            ],
        }

        # =========================================================
        # Same Point 前端 table 設定
        #
        # 注意：
        #   不混進 hourlyTable_key_group。
        #   前端在 same point checkbox 開啟時，應改吃 SamePoint 設定。
        # =========================================================
        self.same_point_table_coldict = {
            "line_id": "PI Line",
            "aoi": "aoi",
            "model": "Model",
            "glass_type": "side",
            "pi_hour": "Hourly",
            "recipe_id": "recipe",

            #"offset": "offset",
            "common_cnt": "common cnt",
            "common_glass_cnt": "common gld",
            "common_points_details": "common points",
            "gen_time": "gen time",
        }

        self.same_point_table_group_key_dict = {
            "main_group": [
                "pi_hour",
                "line_id",
                "aoi",
                "model",
                "glass_type",
                "recipe_id",
                #"offset",
                "common_cnt",
                "common_glass_cnt",
            ],
            "uni_col": [
                "common_points_details",
            ],
        }

        self.same_point_filter_item_coldict = {
            "offset": {
                "key": "offset",
                "label": "offset",
                "values": self.same_point_offsets,
                "default": self.same_point_default_offset,
                "cascade": False,
            },
        }

        self.chart_group_dict = {
            # chart 固定 total 應由前端讀 TabSummaryData。
            # 這裡保留舊 chart.js 結構，避免未改前端時爆掉。
            "left": [
                "line_id",
                "model",
                "glass_type",
                "recipe_total_glass_cnt",
                "def_glass_cnt",
            ],
            "up": [
                "aoi",
                "adc_def_code",
            ],
            "down": [
                "pi_hour",
            ],
            "right": [
                "density",
            ],
        }

        self.uni_glass_row_info_dict = {
            "glass_id": "glass",
            "glass_size_detail": "glass_size_detail",
            "small_defect_count": "S",
            "middle_defect_count": "M",
            "large_defect_count": "L",
            "over_defect_count": "O",
        }

        self.defect_group_coldict = {
            "x": "x",
            "y": "y",
            "chip_name": "chip",
            "pic_name": "img",
        }

        # 全域 filter 不放 offset。
        # offset 只放 SamePoint / Total tab，避免一般 UPI/PISpot/SPS 也顯示 offset。
        self.filter_item_coldict = {
            "line_id": "PI Line",
            "aoi": "aoi tools",
            "model": "Model",
            "glass_type": "glass_side",
            "recipe_id": "recipe",
            "adc_def_code": "defect code",
            "defect_size": "defect size",
        }

        def_col = "adc_def_code"

        self.tab_filter_config = {
            "UPI": {
                "backend_tab_name": "UPI",
                "recipe_family": "UPI",
                "line_id": ["CAPIC200"],
                "aoi": ["aoi100", "aoi200", "aoi300"],
                def_col: self.uni_UPI_defect_codes,
                "recipe_id": [],
            },

            "UPI(Total)": {
                "backend_tab_name": "UPI_Total",
                "recipe_family": "UPI",
                # Same Point only for Total tab
                "same_point": {
                    "enabled": True,
                    "show_checkbox": True,
                    "default_checked": False,

                    "source_table": self.aoi_density_same_point_tbn,

                    "offset_key": "offset",
                    "offset_values": self.same_point_offsets,
                    "default_offset": self.same_point_default_offset,

                    "detail_col": "common_points_details",
                    "metric_cols": {
                        "common_cnt": "common_cnt",
                        "common_glass_cnt": "common_glass_cnt",
                    },

                    "join_keys": [
                        "pi_hour",
                        "line_id",
                        "aoi",
                        "model",
                        "glass_type",
                        "recipe_id",
                    ],
                },

                # 給前端快速建立 offset dropdown 用
                "offset": self.same_point_offsets,

                "line_id": ["CAPIC200"],
                "aoi": ["aoi100", "aoi200", "aoi300"],
                def_col: ["others"],
                "recipe_id": [],
            },

            "PISpot": {
                "backend_tab_name": "PISpot",
                "recipe_family": "PISpot",
                "line_id": ["CAPIC200"],
                "aoi": ["aoi100", "aoi200", "aoi300"],
                def_col: self.uni_SPOT_defect_codes,
                "recipe_id": [],
                "defect_size": ["O", "L"],
            },

            "PISpot(Total)": {
                "backend_tab_name": "PISpot_Total",
                "recipe_family": "PISpot",

                # Same Point only for Total tab
                "same_point": {
                    "enabled": True,
                    "show_checkbox": True,
                    "default_checked": False,

                    "source_table": self.aoi_density_same_point_tbn,

                    "offset_key": "offset",
                    "offset_values": self.same_point_offsets,
                    "default_offset": self.same_point_default_offset,

                    "detail_col": "common_points_details",
                    "metric_cols": {
                        "common_cnt": "common_cnt",
                        "common_glass_cnt": "common_glass_cnt",
                    },

                    "join_keys": [
                        "pi_hour",
                        "line_id",
                        "aoi",
                        "model",
                        "glass_type",
                        "recipe_id",
                    ],
                },

                # 給前端快速建立 offset dropdown 用
                "offset": self.same_point_offsets,

                "line_id": ["CAPIC200"],
                "aoi": ["aoi100", "aoi200", "aoi300"],
                def_col: ["others"],
                "recipe_id": [],
            },

            "SPS": {
                "backend_tab_name": "SPS",
                "recipe_family": "PISpot",
                "line_id": ["CAPIC200"],
                "aoi": ["aoi100", "aoi200", "aoi300"],
                def_col: self.uni_SPS_defect_codes,
                "recipe_id": [],
            },

            "default_spec_table": {
                "type": "table",
                "tab_name": "預設spec",
                "table_columns": {
                    "PI Line": "line_id",
                    "MODEL_ID": "model",
                    "MODEL_TYPE": "MODEL_TYPE",
                    "PROCESS_TYPE": "PROCESS_TYPE",
                    "GLASS_TYPE": "glass_type",
                    "DEFECT_CODE": "adc_def_code",
                    "SIZE_TYPE": "defect_size",
                    "OOC": "OOC",
                    "OOS": "OOS",
                    "Editor": "Editor",
                },
                "filter_item_coldict": {
                    "PI Line": {
                        "key": "line_id",
                        "values": [f"CAPIC{i}00" for i in range(1, 8)],
                    },
                    "MODEL_ID": {
                        "key": "model",
                        "values": [],
                    },
                    "MODEL_TYPE": {
                        "key": "MODEL_TYPE",
                        "values": ["Normal", "高階"],
                    },
                    "PROCESS_TYPE": {
                        "key": "PROCESS_TYPE",
                        "values": [],
                    },
                    "GLASS_TYPE": {
                        "key": "glass_type",
                        "values": ["TFT", "CF"],
                    },
                    "DEFECT_CODE": {
                        "key": "adc_def_code",
                        "values": [],
                    },
                    "SIZE_TYPE": {
                        "key": "defect_size",
                        "values": ["S", "MS", "LMS", "O", "OL", "OLM", "OLMS"],
                    },
                },
            },

            "EditSummary": {
                "type": "table",
                "tab_name": "Action_History",
                "table_columns": [
                    "line_id",
                    "aoi",
                    "model",
                    "glass_type",
                    "recipe_id",
                    "pi_hour",
                    "adc_def_code",
                    "density",
                    "comment",
                    "action",
                    "Editor",
                    "modify_time",
                ],
                "filter_item_coldict": {
                    "line_id": {
                        "key": "line_id",
                        "values": [f"CAPIC{i}00" for i in range(1, 8)],
                    },
                    "model": {
                        "key": "model",
                        "values": [],
                    },
                    "glass_type": {
                        "key": "glass_type",
                        "values": self.glass_sides,
                    },
                },
            },

            "Trend Chart": {
                "type": "Chart",
                "tab_name": "趨勢分析(月週日)",
            },

            "csv_download": {
                "type": "csv",
                "tab_name": "資料下載",
                "table_columns": {
                    "tab_name": "tab",
                    "line_id": "PI Line",
                    "aoi": "aoi",
                    "model": "Model",
                    "glass_type": "glass_side",
                    "pi_hour": "hourly",
                    "recipe_id": "recipe",
                    def_col: "defect code",
                    "tab_total_glass_cnt": "total_glass",
                    "defect_cnt": "defect_cnt",
                    "density": "density",
                },
            },

            "density_average": {
                "type": "density_avg",
                "tab_name": "Density平均值",

                # 使用者需求：density by line、glass_side、Model
                # AOI Density 實際欄位 glass_side = glass_type
                "group_keys": [
                    # "aoi",
                    "glass_type",
                    "line_id",
                    "model",
                    "defect_size",
                ],

                "metric_columns": [
                    "defect_cnt",
                    "total_glass_cnt",
                    "density",
                    "day_count",
                    "hour_count",
                ],

                "time_col": "pi_hour",
                "time_semantic": "pi_hour_label_30min",
                "day_boundary": "07:30",

                "source_columns": {
                    "aoi": "aoi",
                    "glass_side": "glass_type",
                    "line_id": "line_id",
                    "model": "model",
                    "recipe_id": "recipe_id",
                    "defect_code": "adc_def_code",
                    "defect_size": "defect_size",

                    # AOI Density 新三層表的 code summary 欄位
                    # 後端平均值計算可依需求決定用 tab_total_glass_cnt 或 recipe_total_glass_cnt。
                    # 若是 by line/glass_side/model 合併 recipe/code，建議後端用 tab summary 或去重後 total glass。
                    "total_glass_cnt": "tab_total_glass_cnt",
                    "recipe_total_glass_cnt": "recipe_total_glass_cnt",
                    "defect_cnt": "defect_cnt",

                    "small_defect_count": "small_defect_count",
                    "middle_defect_count": "middle_defect_count",
                    "large_defect_count": "large_defect_count",
                    "over_defect_count": "over_defect_count",
                    "glass_size_detail": "glass_size_detail",
                },

                "filter_item_coldict": {
                    "AOI": {
                        "key": "aoi",
                        "values": ["aoi100", "aoi200", "aoi300"],
                        "cascade": True,
                    },
                    "glass_side": {
                        "key": "glass_type",
                        "values": ["TFT", "CF"],
                        "cascade": True,
                    },
                    "PI Line": {
                        "key": "line_id",
                        "values": [f"CAPIC{i}00" for i in range(1, 8)],
                        "cascade": True,
                    },
                    "Model": {
                        "key": "model",
                        "values": [],
                        "cascade": True,
                    },
                    "recipe": {
                        "key": "recipe_id",
                        "values": [],
                        "cascade": True,
                    },
                    "defect code": {
                        "key": "adc_def_code",
                        "values": [],
                        "cascade": True,
                    },
                    "defect size": {
                        "key": "defect_size",
                        "values": ["S", "MS", "LMS", "O", "OL", "OLM", "OLMS"],
                        "cascade": True,
                    },
                },

                # 階層式 filter 順序
                # 日期不放在這裡，因為日期是頁面固定 date range 控制。
                "cascade_order": [
                    "aoi",
                    "glass_type",
                    "line_id",
                    "model",
                    "recipe_id",
                    "adc_def_code",
                    "defect_size",
                ],

                # 若 recipe 勾選到 4碼 0 開頭，defect code 預設只勾 OL
                "recipe_defect_default_rules": [
                    {
                        "name": "PISpot_0xxx_recipe",
                        "when": {
                            "field": "recipe_id",
                            "pattern": r"^0\d{3}$",
                        },
                        "set": {
                            "defect_size": ["OL"],
                        },
                        "mode": "replace",
                    }
                ],

                "table_columns": {
                    # "aoi": "aoi",
                    "glass_type": "glass_side",
                    "line_id": "PI Line",
                    "model": "Model",
                    "defect_size": "SIZE_GROUP",
                    "defect_cnt": "defect count",
                    "total_glass_cnt": "total glass",
                    "density": "density",
                    "day_count": "days",
                    "hour_count": "hours",
                },

                "download_columns": {
                    # "aoi": "aoi",
                    "glass_type": "glass_side",
                    "line_id": "PI Line",
                    "model": "Model",
                    "defect_size": "SIZE_GROUP",
                    "defect_cnt": "defect count",
                    "total_glass_cnt": "total glass",
                    "density": "density",
                    "day_count": "days",
                    "hour_count": "hours",
                },
            },
        }

        self.front_config = {
            "chartKeyDict": self.chart_group_dict,
            "filtetItemKeyDict": self.filter_item_coldict,
            "hourlyTable": self.chart_table_coldict,
            "hourlyTable_key_group": self.table_group_key_dict,
            "uniGlassInfo": self.uni_glass_row_info_dict,
            "uniGlassDefectTable": self.defect_group_coldict,
            "SubTabsFilterDefaultDict": self.tab_filter_config,

            # 新增：Recipe same point config
            "SamePoint": {
                "enabled_tabs": self.same_point_enabled_tabs,
                "source_table": self.aoi_density_same_point_tbn,

                "sql_cols": self.aoi_density_same_point_sql_cols,
                "api_cols": self.aoi_density_same_point_api_cols,

                "offset_key": "offset",
                "offset_values": self.same_point_offsets,
                "default_offset": self.same_point_default_offset,

                "detail_col": "common_points_details",
                "metric_cols": {
                    "common_cnt": "common_cnt",
                    "common_glass_cnt": "common_glass_cnt",
                },

                "table_columns": self.same_point_table_coldict,
                "table_key_group": self.same_point_table_group_key_dict,
                "filter_item_coldict": self.same_point_filter_item_coldict,

                "join_keys": [
                    "pi_hour",
                    "line_id",
                    "aoi",
                    "model",
                    "glass_type",
                    "recipe_id",
                ],
            },
        }

    def spec_table_process(self, dbhandler):
        # default spec table
        default_spec_tb = dbhandler.get_rows("default_spec_table", {"drop": "F"})
        default_df = pd.DataFrame(default_spec_tb)

        if not default_df.empty:
            key_cols = [
                "line_id",
                "model",
                "glass_type",
                "adc_def_code",
                "defect_size",
                "MODEL_TYPE",
            ]
            default_df["modify_time"] = pd.to_datetime(default_df["modify_time"], errors="coerce")
            default_df.sort_values(by=key_cols + ["modify_time"], ascending=False, inplace=True)
            default_df = default_df.drop_duplicates(subset=key_cols, keep="first").reset_index(drop=True)
            default_df = default_df.fillna("")
        else:
            default_df = pd.DataFrame(columns=self.default_spec_table_cols)

        # fixed spec table
        """
        yyyymm = datetime.now().strftime("%Y%m")
        fixed_df = dbhandler.get_runs_delta_days(f"fix_spec_table_{yyyymm}", days=1, time_col="GEN_DT")
        fixed_df = pd.DataFrame(fixed_df)

        if not fixed_df.empty:
            fixed_df = fixed_df.dropna(axis=0, how="any").reset_index(drop=True)
        else:
            fixed_df = pd.DataFrame(columns=self.fixed_spec_table_cols)
        """

        spec_table_dict = {}

        for data, key in zip(
            [default_df],
            ["default_spec_table"],
        ):
            rows = data.to_dict(orient="index")
            spec_table_dict[key] = rows

        return spec_table_dict


if __name__ == "__main__":
    api_cfg = API_Config()

    print("aoi_density_tab_tbn =", api_cfg.aoi_density_tab_tbn)
    print("aoi_density_recipe_tbn =", api_cfg.aoi_density_recipe_tbn)
    print("aoi_density_code_tbn =", api_cfg.aoi_density_code_tbn)
    print("aoi_density_same_point_tbn =", api_cfg.aoi_density_same_point_tbn)
    print("same_point_offsets =", api_cfg.same_point_offsets)
    print("same_point_enabled_tabs =", api_cfg.same_point_enabled_tabs)