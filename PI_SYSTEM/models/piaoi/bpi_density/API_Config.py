# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd

from models.piaoi.bpi_density.build_bpi_density_job import Config as BPIDensityJobConfig
from models.sql_db_connect import MySQLConnet


@dataclass
class API_Config:
    """
    BPI Area API config.

    System tab:
      來料檢(BPI/同點)

    Function groups:
      1. bpi_density
         原 BPI Density 功能

      2. bpi_same_point
         BPI/API 同片同點來料檢功能

    bpi_same_point 新版重點：
      - pair table 新增 tab / default_offset_um / matched_points_json
      - pair table 不再使用 offset_summary_json
      - offset summary 不再使用 bpi_match_rate / api_match_rate
      - offset summary 不再使用 matched_s/m/l/o_count
      - offset summary 改用 matched_bpi_* 與 matched_api_* size count
      - offset summary 新增 matched_size_transition_json
      - match detail 新增 tab
      - manual/editor 保留 key：
          model + glass_side + glass_id + tab + api_aoi + api_recipe_id
    """

    bpi_job_cfg: BPIDensityJobConfig = field(default_factory=BPIDensityJobConfig)

    # =========================================================
    # Runtime
    # =========================================================
    now: datetime = field(default_factory=datetime.now)

    # =========================================================
    # Common fixed options
    # =========================================================
    common_aoi_values: List[str] = field(default_factory=lambda: [f"aoi{i}00" for i in range(1, 4)])
    common_glass_sides: List[str] = field(default_factory=lambda: ["CF", "TFT"])

    # Density 用 size group
    common_size_group_options: List[str] = field(default_factory=lambda: ["S", "MS", "LMS", "O", "OL", "OLM", "OLMS"])

    # Same Point 點位層級 size filter 用單一尺寸
    common_defect_sizes: List[str] = field(default_factory=lambda: ["S", "M", "L", "O"])

    common_pi_types: List[str] = field(default_factory=lambda: ["BPI"])
    common_same_point_offsets: List[int] = field(default_factory=lambda: list(range(5, 55, 5)))

    # =========================================================
    # BPI Density DB / table names
    # =========================================================
    bpi_density_db_name: str = ""
    bpi_density_summary_table_tpl: str = "bpi_api_summary_yyyymm"
    bpi_density_summary_tbn: str = ""
    bpi_density_default_spec_tbn: str = "default_spec_table"

    # =========================================================
    # BPI Density columns
    # =========================================================
    bpi_density_summary_sql_cols: List[str] = field(default_factory=list)
    bpi_density_summary_api_cols: List[str] = field(default_factory=list)

    bpi_density_default_spec_sql_cols: List[str] = field(default_factory=list)
    bpi_density_default_spec_api_cols: List[str] = field(default_factory=list)

    bpi_density_primary_group_cols: List[str] = field(default_factory=lambda: [
        "scan_hour",
        "aoi",
        "model",
        "cassette_id",
        "glass_side",
        "recipe_id",
    ])

    # =========================================================
    # BPI Density front-end configs
    # =========================================================
    bpi_density_chart_table_coldict: Dict[str, str] = field(default_factory=dict)
    bpi_density_table_group_key_dict: Dict[str, List[str]] = field(default_factory=dict)
    bpi_density_chart_group_dict: Dict[str, List[str]] = field(default_factory=dict)
    bpi_density_uni_glass_row_info_dict: Dict[str, str] = field(default_factory=dict)
    bpi_density_filter_item_coldict: Dict[str, str] = field(default_factory=dict)

    # =========================================================
    # BPI/API Same Point DB / table names
    # =========================================================
    bpi_same_point_db_name: str = "piaoi_bpi_same_point"

    bpi_same_point_pair_table_tpl: str = "bpi_same_point_yyyymm"
    bpi_same_point_offset_table_tpl: str = "bpi_same_point_offset_summary_yyyymm"
    bpi_same_point_match_table_tpl: str = "bpi_same_point_match_detail_yyyymm"

    bpi_same_point_pair_tbn: str = ""
    bpi_same_point_offset_tbn: str = ""
    bpi_same_point_match_tbn: str = ""

    bpi_same_point_default_spec_tbn: str = "default_spec_table"

    # =========================================================
    # BPI/API Same Point columns
    # =========================================================
    bpi_same_point_pair_sql_cols: List[str] = field(default_factory=list)
    bpi_same_point_pair_api_cols: List[str] = field(default_factory=list)

    bpi_same_point_offset_sql_cols: List[str] = field(default_factory=list)
    bpi_same_point_offset_api_cols: List[str] = field(default_factory=list)

    bpi_same_point_match_sql_cols: List[str] = field(default_factory=list)
    bpi_same_point_match_api_cols: List[str] = field(default_factory=list)

    bpi_same_point_default_spec_sql_cols: List[str] = field(default_factory=list)
    bpi_same_point_default_spec_api_cols: List[str] = field(default_factory=list)

    # =========================================================
    # BPI/API Same Point front-end configs
    # =========================================================
    bpi_same_point_chart_group_dict: Dict[str, List[str]] = field(default_factory=dict)
    bpi_same_point_chart_table_coldict: Dict[str, str] = field(default_factory=dict)
    bpi_same_point_table_group_key_dict: Dict[str, List[str]] = field(default_factory=dict)
    bpi_same_point_filter_item_coldict: Dict[str, str] = field(default_factory=dict)
    bpi_same_point_defect_map_config: Dict[str, Any] = field(default_factory=dict)

    # =========================================================
    # Common tab config / front config
    # =========================================================
    tab_group_config: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    tab_filter_config: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    front_config: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        ym = self.now.strftime("%Y%m")

        # =========================================================
        # BPI Density DB / table names
        # =========================================================
        self.bpi_density_db_name = "piaoi_bpi_density"
        self.bpi_density_summary_table_tpl = "bpi_api_summary_yyyymm"
        self.bpi_density_summary_tbn = self.bpi_density_summary_table_tpl.replace("yyyymm", ym)
        self.bpi_density_default_spec_tbn = "default_spec_table"

        # =========================================================
        # BPI/API Same Point DB / table names
        # =========================================================
        self.bpi_same_point_db_name = "piaoi_bpi_same_point"
        self.bpi_same_point_pair_tbn = self.bpi_same_point_pair_table_tpl.replace("yyyymm", ym)
        self.bpi_same_point_offset_tbn = self.bpi_same_point_offset_table_tpl.replace("yyyymm", ym)
        self.bpi_same_point_match_tbn = self.bpi_same_point_match_table_tpl.replace("yyyymm", ym)
        self.bpi_same_point_default_spec_tbn = "default_spec_table"

        # =========================================================
        # BPI Density summary columns
        # =========================================================
        self.bpi_density_summary_sql_cols = [
            "aoi",
            "model",
            "scan_hour",
            "cassette_id",
            "glass_side",
            "recipe_id",
            "pi_type",
            "run_day",
            "glass_count",
            "total_defect_count",
            "small_defect_count",
            "middle_defect_count",
            "large_defect_count",
            "over_defect_count",
            "density",
            "glass_list",
            "glass_size_detail",
            "source_db",
            "source_table",
            "comment",
            "action",
            "editor",
            "modify_time",
        ]

        self.bpi_density_summary_api_cols = [
            "aoi",
            "model",
            "scan_hour",
            "cassette_id",
            "glass_side",
            "recipe_id",
            "pi_type",
            "run_day",
            "glass_count",
            "total_defect_count",
            "small_defect_count",
            "middle_defect_count",
            "large_defect_count",
            "over_defect_count",
            "density",
            "glass_list",
            "glass_size_detail",
            "comment",
            "action",
            "editor",
            "modify_time",
            "size_mask",
        ]

        # =========================================================
        # BPI Density default spec columns
        # =========================================================
        self.bpi_density_default_spec_sql_cols = [
            "model",
            "glass_type",
            "defect_size",
            "OOC",
            "OOS",
            "Editor",
            "modify_time",
            "drop",
        ]
        self.bpi_density_default_spec_api_cols = self.bpi_density_default_spec_sql_cols[:-1]

        # =========================================================
        # BPI/API Same Point pair columns - new schema
        # =========================================================
        self.bpi_same_point_pair_sql_cols = [
            "model",
            "glass_side",
            "glass_id",
            "scan_hour",
            "run_day",
            "tab",

            "bpi_aoi",
            "bpi_line_id",
            "bpi_recipe_id",
            "bpi_cassette_id",
            "bpi_scan_time",
            "bpi_pi_time",
            "bpi_scan_hour",
            "bpi_run_day",
            "bpi_source_db",
            "bpi_source_table",

            "api_aoi",
            "api_line_id",
            "api_recipe_id",
            "api_cassette_id",
            "api_scan_time",
            "api_pi_time",
            "api_scan_hour",
            "api_run_day",
            "api_source_db",
            "api_source_table",

            "bpi_defect_count",
            "api_defect_count",

            "bpi_small_defect_count",
            "bpi_middle_defect_count",
            "bpi_large_defect_count",
            "bpi_over_defect_count",

            "api_small_defect_count",
            "api_middle_defect_count",
            "api_large_defect_count",
            "api_over_defect_count",

            "pair_status",
            "pair_message",
            "default_offset_um",
            "matched_points_json",

            "comment",
            "action",
            "editor",
            "modify_time",

            "gen_time",
        ]
        self.bpi_same_point_pair_api_cols = self.bpi_same_point_pair_sql_cols[:]

        # =========================================================
        # BPI/API Same Point offset summary columns - new schema
        # =========================================================
        self.bpi_same_point_offset_sql_cols = [
            "model",
            "glass_side",
            "glass_id",
            "scan_hour",
            "run_day",
            "tab",

            "bpi_aoi",
            "bpi_scan_time",
            "bpi_recipe_id",

            "api_aoi",
            "api_scan_time",
            "api_recipe_id",

            "offset_um",

            "bpi_defect_count",
            "api_defect_count",
            "matched_pair_count",
            "matched_bpi_defect_count",
            "matched_api_defect_count",
            "unmatched_bpi_defect_count",
            "unmatched_api_defect_count",

            "matched_bpi_s_count",
            "matched_bpi_m_count",
            "matched_bpi_l_count",
            "matched_bpi_o_count",

            "matched_api_s_count",
            "matched_api_m_count",
            "matched_api_l_count",
            "matched_api_o_count",

            "matched_size_transition_json",

            "gen_time",
        ]
        self.bpi_same_point_offset_api_cols = self.bpi_same_point_offset_sql_cols[:]

        # =========================================================
        # BPI/API Same Point match detail columns - new schema
        # =========================================================
        self.bpi_same_point_match_sql_cols = [
            "model",
            "glass_side",
            "glass_id",
            "scan_hour",
            "run_day",
            "tab",

            "bpi_aoi",
            "bpi_line_id",
            "bpi_recipe_id",
            "bpi_scan_time",

            "api_aoi",
            "api_line_id",
            "api_recipe_id",
            "api_scan_time",

            "offset_um",

            "bpi_defect_uid",
            "bpi_chip_id",
            "bpi_x",
            "bpi_y",
            "bpi_defect_size",
            "bpi_adc_def_code",
            "bpi_retype_code",
            "bpi_pic_path",
            "bpi_pic_name",

            "api_defect_uid",
            "api_chip_id",
            "api_x",
            "api_y",
            "api_defect_size",
            "api_adc_def_code",
            "api_retype_code",
            "api_pic_path",
            "api_pic_name",

            "dx",
            "dy",
            "distance",
            "match_rank",
            "match_method",
            "gen_time",
        ]
        self.bpi_same_point_match_api_cols = self.bpi_same_point_match_sql_cols[:]

        # =========================================================
        # BPI/API Same Point default spec columns
        # =========================================================
        self.bpi_same_point_default_spec_sql_cols = [
            "model",
            "glass_side",
            "defect_size",
            "OOC",
            "OOS",
            "editor",
            "modify_time",
            "drop",
        ]
        self.bpi_same_point_default_spec_api_cols = self.bpi_same_point_default_spec_sql_cols[:-1]

        # =========================================================
        # BPI Density front configs
        # =========================================================
        self.bpi_density_chart_table_coldict = {
            "aoi": "AOI",
            "model": "Model",
            "scan_hour": "Hourly",
            "cassette_id": "CST",
            "glass_side": "glass_side",
            "recipe_id": "recipe",
            "glass_count": "total gld",
            "total_defect_count": "def cnt",
            "density": "density",
            "glass_list": "glass",
            "glass_size_detail": "size",
            "comment": "comment",
            "action": "action",
            "editor": "Editor",
            "modify_time": "modify_time",
        }

        self.bpi_density_table_group_key_dict = {
            "main_group": [
                "scan_hour",
                "aoi",
                "model",
                "cassette_id",
                "glass_side",
                "recipe_id",
                "glass_count",
                "total_defect_count",
                "density",
                "comment",
                "action",
                "editor",
                "modify_time",
            ],
            "uni_col": [
                "glass_size_detail",
                "glass_list",
            ],
        }

        self.bpi_density_chart_group_dict = {
            "left": ["aoi", "model", "glass_side", "glass_count"],
            "up": ["cassette_id", "recipe_id"],
            "down": ["scan_hour"],
            "right": ["density"],
        }

        self.bpi_density_uni_glass_row_info_dict = {
            "glass_id": "glass",
            "glass_size_detail": "glass_size_detail",
            "small_defect_count": "S",
            "middle_defect_count": "M",
            "large_defect_count": "L",
            "over_defect_count": "O",
        }

        self.bpi_density_filter_item_coldict = {
            "aoi": "aoi",
            "model": "Model",
            "glass_side": "glass_side",
            "recipe_id": "recipe",
            "defect_size": "defect size",
        }

        # =========================================================
        # BPI/API Same Point front configs - new schema
        # =========================================================
        self.bpi_same_point_chart_group_dict = {
            "left": ["model", "glass_side", "glass_id", "tab"],
            "up": ["offset_um"],
            "down": ["scan_hour", "glass_id"],
            "bar": ["bpi_defect_count", "api_defect_count"],
            "right": ["matched_pair_count"],
        }

        self.bpi_same_point_chart_table_coldict = {
            "scan_hour": "Hourly",
            "run_day": "run_day",
            "tab": "tab",
            "model": "Model",
            "glass_side": "side",
            "glass_id": "glass",

            "bpi_aoi": "BPI AOI",
            "bpi_scan_time": "BPI scan time",
            "bpi_recipe_id": "BPI recipe",
            "bpi_defect_count": "BPI defect",

            "api_aoi": "API AOI",
            "api_scan_time": "API scan time",
            "api_recipe_id": "API recipe",
            "api_defect_count": "API defect",

            "default_offset_um": "default offset",
            "offset_um": "offset",
            "matched_pair_count": "same point",
            "matched_bpi_defect_count": "matched BPI",
            "matched_api_defect_count": "matched API",
            "unmatched_bpi_defect_count": "unmatched BPI",
            "unmatched_api_defect_count": "unmatched API",

            "matched_bpi_s_count": "BPI S",
            "matched_bpi_m_count": "BPI M",
            "matched_bpi_l_count": "BPI L",
            "matched_bpi_o_count": "BPI O",

            "matched_api_s_count": "API S",
            "matched_api_m_count": "API M",
            "matched_api_l_count": "API L",
            "matched_api_o_count": "API O",

            "comment": "comment",
            "action": "action",
            "editor": "Editor",
            "modify_time": "modify_time",
        }

        self.bpi_same_point_table_group_key_dict = {
            "main_group": [
                "scan_hour",
                "run_day",
                "tab",
                "model",
                "glass_side",
                "glass_id",

                "comment",
                "action",
                "editor",
                "modify_time",

                "bpi_aoi",
                "bpi_scan_time",
                "bpi_recipe_id",
                "bpi_defect_count",

                "api_aoi",
                "api_scan_time",
                "api_recipe_id",
                "api_defect_count",

                "default_offset_um",
                "matched_points_json",
            ],
            "offset_group": [
                "offset_um",
                "matched_pair_count",
                "matched_bpi_defect_count",
                "matched_api_defect_count",
                "unmatched_bpi_defect_count",
                "unmatched_api_defect_count",

                "matched_bpi_s_count",
                "matched_bpi_m_count",
                "matched_bpi_l_count",
                "matched_bpi_o_count",

                "matched_api_s_count",
                "matched_api_m_count",
                "matched_api_l_count",
                "matched_api_o_count",

                "matched_size_transition_json",
            ],
            "uni_col": [],
        }

        self.bpi_same_point_filter_item_coldict = {
            "date": "日期(API SCANTIME)",
            "api_aoi": "AOI(API)",
            "model": "Model",
            "api_recipe_id": "recipe(API)",
            "glass_side": "glass_side",
            "defect_size": "defect size(同點)",
            "offset_um": "offset",
        }

        self.bpi_same_point_defect_map_config = {
            "modes": [
                {"key": "BPI", "label": "BPI"},
                {"key": "API", "label": "API"},
                {"key": "MATCH", "label": "同點"},
            ],
            "default_mode": "MATCH",

            # Same Point size filter 是點位層級：
            # selected size 命中 bpi_defect_size OR api_defect_size 即顯示。
            "size_filter": self.common_defect_sizes[:],
            "size_filter_logic": "bpi_or_api",
            "size_filter_fields": [
                "bpi_defect_size",
                "api_defect_size",
            ],

            "offsets": self.common_same_point_offsets[:],
            "default_offset": 20,

            # pair table 內 default offset 快取欄位
            "default_offset_field": "default_offset_um",
            "matched_points_field": "matched_points_json",

            # 非 default offset 或需要完整明細時查 match detail
            "match_detail_table_tpl": self.bpi_same_point_match_table_tpl,

            "map_axis": {
                "minX": 0,
                "maxX": 1850000,
                "minY": 0,
                "maxY": 1500000,
            },

            # 給 map / 精準 row 使用，不是 editor key
            "pair_key_cols": [
                "model",
                "glass_side",
                "glass_id",
                "tab",
                "api_aoi",
                "api_recipe_id",
                "api_scan_time",
            ],

            # 給 comment/action 保留用
            "manual_key_cols": [
                "model",
                "glass_side",
                "glass_id",
                "tab",
                "api_aoi",
                "api_recipe_id",
            ],

            "match_detail_columns": {
                "offset_um": "offset_um",

                "bpi_x": "bpi_x",
                "bpi_y": "bpi_y",
                "bpi_defect_size": "bpi_defect_size",
                "bpi_adc_def_code": "bpi_adc_def_code",
                "bpi_retype_code": "bpi_retype_code",
                "bpi_pic_path": "bpi_pic_path",
                "bpi_pic_name": "bpi_pic_name",

                "api_x": "api_x",
                "api_y": "api_y",
                "api_defect_size": "api_defect_size",
                "api_adc_def_code": "api_adc_def_code",
                "api_retype_code": "api_retype_code",
                "api_pic_path": "api_pic_path",
                "api_pic_name": "api_pic_name",

                "dx": "dx",
                "dy": "dy",
                "distance": "distance",
                "match_rank": "match_rank",
            },

            # 舊 defect columns 保留給兼容舊 map code，如已完全改版可移除。
            "defect_columns": {
                "x": "x",
                "y": "y",
                "defect_size": "defect_size",
                "adc_def_code": "adc_def_code",
                "pic_path": "pic_path",
                "pic_name": "pic_name",
            },
        }

        # =========================================================
        # Sub tab group config
        # =========================================================
        self.tab_group_config = {
            "bpi_density": {
                "label": "BPI",
                "order": 1,
            },
            "bpi_same_point": {
                "label": "同點",
                "order": 2,
            },
        }

        # =========================================================
        # Tab configs
        # =========================================================
        self.tab_filter_config = self._build_tab_filter_config()

        # =========================================================
        # Front Config
        # =========================================================
        self.front_config = self._build_front_config()

    # =============================================================================
    # Same Point tab builder
    # =============================================================================
    def _build_same_point_hourly_tab(
        self,
        *,
        tab_order: int,
        tab_name: str,
        same_point_page: str,
        recipe_four_digit_prefix: List[str],
    ) -> Dict[str, Any]:
        return {
            "type": "hourly",
            "tab_group": "bpi_same_point",
            "tab_order": tab_order,
            "tab_name": tab_name,

            "system_key": "bpi_same_point",
            "same_point_page": same_point_page,
            "section_id": "bpi-same-point-root",

            "db_name": self.bpi_same_point_db_name,
            "pair_table_tpl": self.bpi_same_point_pair_table_tpl,
            "offset_table_tpl": self.bpi_same_point_offset_table_tpl,
            "match_table_tpl": self.bpi_same_point_match_table_tpl,

            "default_days": 3,
            "time_col": "scan_hour",
            "time_semantic": "api_scan_hour_label_30min",
            "day_boundary": "07:30",

            "offsets": self.common_same_point_offsets[:],
            "default_offset": 20,

            "recipe_rule": {
                "four_digit_prefix": recipe_four_digit_prefix[:],
                "three_digit": True,
                "api_recipe_field": "api_recipe_id",
                "bpi_recipe_field": "bpi_recipe_id",
            },

            "chart_config": {
                "x_axis": ["scan_hour", "glass_id"],
                "bar_series": {
                    "BPI": "bpi_defect_count",
                    "API": "api_defect_count",
                },
                "point_series": {
                    "same_point": "matched_pair_count",
                },
                "default_offset": 20,
                "grouping": [
                    "scan_hour",
                    "tab",
                    "model",
                    "glass_side",
                    "glass_id",
                    "bpi_aoi",
                    "bpi_recipe_id",
                    "bpi_scan_time",
                    "api_aoi",
                    "api_recipe_id",
                    "api_scan_time",
                    "offset_um",
                ],
            },

            "filter_item_coldict": {
                "日期": {
                    "key": "date",
                    "type": "date_range",
                },
                "tab": {
                    "key": "tab",
                    "values": [tab_name],
                    "default": tab_name,
                    "hidden": True,
                },
                "API AOI": {
                    "key": "api_aoi",
                    "values": self.common_aoi_values[:],
                    "cascade": True,
                },
                "Model": {
                    "key": "model",
                    "values": [],
                    "cascade": True,
                },
                "API recipe": {
                    "key": "api_recipe_id",
                    "values": [],
                    "cascade": True,
                },
                "glass_side": {
                    "key": "glass_side",
                    "values": self.common_glass_sides[:],
                    "cascade": True,
                },
                "defect size": {
                    "key": "defect_size",
                    "values": self.common_defect_sizes[:],
                    "cascade": True,
                    "match_logic": "bpi_or_api",
                    "match_fields": ["bpi_defect_size", "api_defect_size"],
                },
                "Offset": {
                    "key": "offset_um",
                    "values": self.common_same_point_offsets[:],
                    "default": 20,
                },
            },

            "cascade_order": [
                "api_aoi",
                "glass_side",
                "model",
                "api_recipe_id",
                "defect_size",
                "offset_um",
            ],

            "table_columns": {
                "shared_left": [
                    {
                        "key": "scan_hour",
                        "label": "Hourly",
                    },
                    {
                        "key": "tab",
                        "label": "tab",
                    },
                    {
                        "key": "model",
                        "label": "Model",
                    },
                    {
                        "key": "glass_side",
                        "label": "side",
                    },
                    {
                        "key": "glass_id",
                        "label": "glass",
                    },
                ],

                "compare": [
                    {
                        "label": "AOI",
                        "bpi_key": "bpi_aoi",
                        "api_key": "api_aoi",
                    },
                    {
                        "label": "scan time",
                        "bpi_key": "bpi_scan_time",
                        "api_key": "api_scan_time",
                    },
                    {
                        "label": "recipe",
                        "bpi_key": "bpi_recipe_id",
                        "api_key": "api_recipe_id",
                    },
                    {
                        "label": "defect",
                        "bpi_key": "bpi_defect_count",
                        "api_key": "api_defect_count",
                    },
                    {
                        "label": "S",
                        "bpi_key": "matched_bpi_s_count",
                        "api_key": "matched_api_s_count",
                    },
                    {
                        "label": "M",
                        "bpi_key": "matched_bpi_m_count",
                        "api_key": "matched_api_m_count",
                    },
                    {
                        "label": "L",
                        "bpi_key": "matched_bpi_l_count",
                        "api_key": "matched_api_l_count",
                    },
                    {
                        "label": "O",
                        "bpi_key": "matched_bpi_o_count",
                        "api_key": "matched_api_o_count",
                    },
                ],

                "shared_right": [
                    {
                        "key": "offset_um",
                        "label": "offset",
                        "suffix": "um",
                    },
                    {
                        "key": "matched_pair_count",
                        "label": "same point",
                    },
                ],

                "meta": [
                    {
                        "key": "comment",
                        "label": "comment",
                    },
                    {
                        "key": "action",
                        "label": "action",
                    },
                    {
                        "key": "editor",
                        "label": "Editor",
                    },
                    {
                        "key": "modify_time",
                        "label": "modify_time",
                    },
                ],
            },

            "defect_map": self.bpi_same_point_defect_map_config,
        }

    # =============================================================================
    # Tab configs
    # =============================================================================
    def _build_tab_filter_config(self) -> Dict[str, Dict[str, Any]]:
        return {
            # -----------------------------------------------------
            # Group 1: BPI Density
            # -----------------------------------------------------
            "bpi_density_main": {
                "type": "hourly",
                "tab_group": "bpi_density",
                "tab_order": 10,
                "tab_name": "Hourly",

                "AOI": {
                    "key": "aoi",
                    "values": self.common_aoi_values[:],
                },
                "Model": {
                    "key": "model",
                    "values": [],
                },
                "glass_side": {
                    "key": "glass_side",
                    "values": self.common_glass_sides[:],
                },
                "recipe": {
                    "key": "recipe_id",
                    "values": [],
                },
                "defect_size": {
                    "key": "defect_size",
                    "values": [],
                },
            },

            "bpi_density_action_history": {
                "type": "table",
                "tab_group": "bpi_density",
                "tab_order": 20,
                "tab_name": "Action_History",

                "system_key": "bpi_density",
                "source_table_type": "summary",
                "editable": True,

                "db_name": self.bpi_density_db_name,
                "table_tpl": self.bpi_density_summary_table_tpl,
                "time_col": "scan_hour",

                "editor_match_keys": [
                    "scan_hour",
                    "aoi",
                    "model",
                    "cassette_id",
                    "glass_side",
                    "recipe_id",
                ],
                "editor_col": "editor",
                "editor_requires_time_key": True,

                "table_columns": [
                    "aoi",
                    "model",
                    "scan_hour",
                    "cassette_id",
                    "glass_side",
                    "recipe_id",
                    "density",
                    "comment",
                    "action",
                    "editor",
                    "modify_time",
                ],

                "longtext_columns": [
                    "comment",
                    "action",
                ],

                "filter_item_coldict": {
                    "aoi": {
                        "key": "aoi",
                        "values": self.common_aoi_values[:],
                    },
                    "model": {
                        "key": "model",
                        "values": [],
                    },
                    "glass_side": {
                        "key": "glass_side",
                        "values": self.common_glass_sides[:],
                    },
                    "recipe": {
                        "key": "recipe_id",
                        "values": [],
                    },
                    "defect_size": {
                        "key": "defect_size",
                        "values": [],
                    },
                },
            },

            "bpi_density_default_spec": {
                "type": "table",
                "tab_group": "bpi_density",
                "tab_order": 30,
                "tab_name": "預設spec",

                "system_key": "bpi_density",
                "source_table_type": "default_spec",
                "editable": True,

                "db_name": self.bpi_density_db_name,
                "table_name": self.bpi_density_default_spec_tbn,

                "spec_key_cols": [
                    "model",
                    "glass_type",
                    "defect_size",
                ],
                "editor_col": "Editor",

                "table_columns": {
                    "MODEL_ID": "model",
                    "GLASS_TYPE": "glass_type",
                    "SIZE_TYPE": "defect_size",
                    "OOC": "OOC",
                    "OOS": "OOS",
                    "Editor": "Editor",
                },

                "filter_item_coldict": {
                    "MODEL_ID": {
                        "key": "model",
                        "values": [],
                    },
                    "GLASS_TYPE": {
                        "key": "glass_type",
                        "values": ["TFT", "CF"],
                    },
                    "SIZE_TYPE": {
                        "key": "defect_size",
                        "values": self.common_size_group_options[:],
                    },
                },
            },

            "bpi_density_csv_download": {
                "type": "csv",
                "tab_group": "bpi_density",
                "tab_order": 40,
                "tab_name": "資料下載",
                "system_key": "bpi_density",

                "table_columns": {
                    "aoi": "aoi",
                    "model": "Model",
                    "glass_side": "glass_side",
                    "scan_hour": "hourly",
                    "recipe_id": "recipe",
                    "total_glass_cnt": "total_glass",
                    "defect_cnt": "defect_cnt",
                    "density": "density",
                },
            },

            "bpi_density_average": {
                "type": "density_avg",
                "tab_group": "bpi_density",
                "tab_order": 50,
                "tab_name": "Density平均值",

                "system_key": "bpi_density",

                "group_keys": [
                    "glass_side",
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

                "time_col": "scan_hour",
                "time_semantic": "scan_hour",
                "day_boundary": "07:30",

                "source_columns": {
                    "aoi": "aoi",
                    "glass_side": "glass_side",
                    "model": "model",
                    "recipe_id": "recipe_id",

                    "total_glass_cnt": "glass_count",
                    "defect_cnt": "total_defect_count",

                    "small_defect_count": "small_defect_count",
                    "middle_defect_count": "middle_defect_count",
                    "large_defect_count": "large_defect_count",
                    "over_defect_count": "over_defect_count",
                    "glass_size_detail": "glass_size_detail",
                },

                "filter_item_coldict": {
                    "AOI": {
                        "key": "aoi",
                        "values": self.common_aoi_values[:],
                        "cascade": True,
                    },
                    "glass_side": {
                        "key": "glass_side",
                        "values": self.common_glass_sides[:],
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
                    "defect size": {
                        "key": "defect_size",
                        "values": self.common_size_group_options[:],
                        "cascade": True,
                    },
                },

                "cascade_order": [
                    "aoi",
                    "glass_side",
                    "model",
                    "recipe_id",
                    "defect_size",
                ],

                "recipe_defect_default_rules": [],

                "table_columns": {
                    "glass_side": "glass_side",
                    "model": "Model",
                    "defect_size": "SIZE_GROUP",
                    "defect_cnt": "defect count",
                    "total_glass_cnt": "total glass",
                    "density": "density",
                    "day_count": "days",
                    "hour_count": "hours",
                },

                "download_columns": {
                    "glass_side": "glass_side",
                    "model": "Model",
                    "defect_size": "SIZE_GROUP",
                    "defect_cnt": "defect count",
                    "total_glass_cnt": "total glass",
                    "density": "density",
                    "day_count": "days",
                    "hour_count": "hours",
                },
            },

            # -----------------------------------------------------
            # Group 2: BPI/API Same Point
            # -----------------------------------------------------
            "bpi_same_point_pispot": self._build_same_point_hourly_tab(
                tab_order=10,
                tab_name="PISpot",
                same_point_page="PISpot",
                recipe_four_digit_prefix=["0", "1", "4", "5"],
            ),

            "bpi_same_point_upi": self._build_same_point_hourly_tab(
                tab_order=20,
                tab_name="UPI",
                same_point_page="UPI",
                recipe_four_digit_prefix=["2", "3", "4", "5"],
            ),

            "bpi_same_point_action_history": {
                "type": "table",
                "tab_group": "bpi_same_point",
                "tab_order": 30,
                "tab_name": "Action_History",

                "system_key": "bpi_same_point",
                "source_table_type": "pair",
                "editable": True,

                "db_name": self.bpi_same_point_db_name,
                "table_tpl": self.bpi_same_point_pair_table_tpl,
                "time_col": "scan_hour",

                "editor_match_keys": [
                    "model",
                    "glass_side",
                    "glass_id",
                    "tab",
                    "api_aoi",
                    "api_recipe_id",
                ],
                "editor_col": "editor",
                "editor_requires_time_key": False,

                "manual_key_cols": [
                    "model",
                    "glass_side",
                    "glass_id",
                    "tab",
                    "api_aoi",
                    "api_recipe_id",
                ],

                # 顯示欄位
                "table_columns": [
                    "run_day",
                    "tab",
                    "model",
                    "glass_side",
                    "glass_id",
                    "api_aoi",
                    "api_recipe_id",
                    "comment",
                    "action",
                    "editor",
                    "modify_time",
                ],

                # 不顯示但前端儲存 / 篩選需要保留的欄位
                "hidden_columns": [
                    "scan_hour",
                    "api_recipe_id",
                ],

                "longtext_columns": [
                    "comment",
                    "action",
                ],

                "filter_item_coldict": {
                    "tab": {
                        "key": "tab",
                        "values": [], #"PISpot", "UPI"
                    },
                    "model": {
                        "key": "model",
                        "values": [],
                    },
                    "glass_side": {
                        "key": "glass_side",
                        "values": self.common_glass_sides[:],
                    },
                    "API AOI": {
                        "key": "api_aoi",
                        "values": self.common_aoi_values[:],
                    },
                },
            },


            "bpi_same_point_default_spec": {
                "type": "table",
                "tab_group": "bpi_same_point",
                "tab_order": 40,
                "tab_name": "預設spec",

                "system_key": "bpi_same_point",
                "source_table_type": "default_spec",
                "editable": True,

                "db_name": self.bpi_same_point_db_name,
                "table_name": self.bpi_same_point_default_spec_tbn,

                "spec_key_cols": [
                    "model",
                    "glass_side",
                    "defect_size",
                ],
                "editor_col": "editor",

                "table_columns": {
                    "MODEL_ID": "model",
                    "GLASS_TYPE": "glass_side",
                    "SIZE_TYPE": "defect_size",
                    "OOC": "OOC",
                    "OOS": "OOS",
                    "editor": "editor",
                },

                "filter_item_coldict": {
                    "MODEL_ID": {
                        "key": "model",
                        "values": [],
                    },
                    "GLASS_TYPE": {
                        "key": "glass_side",
                        "values": self.common_glass_sides[:],
                    },
                    "SIZE_TYPE": {
                        "key": "defect_size",
                        "values": self.common_size_group_options[:],
                    },
                },
            },

            "bpi_same_point_csv_download": {
                "type": "csv",
                "tab_group": "bpi_same_point",
                "tab_order": 50,
                "tab_name": "資料下載",

                "system_key": "bpi_same_point",

                "table_columns": {
                    "scan_hour": "Hourly",
                    "run_day": "run_day",
                    "tab": "tab",
                    "model": "Model",
                    "glass_side": "side",
                    "glass_id": "glass",

                    "bpi_aoi": "BPI AOI",
                    "bpi_scan_time": "BPI scan time",
                    "bpi_recipe_id": "BPI recipe",
                    "bpi_defect_count": "BPI defect",

                    "api_aoi": "API AOI",
                    "api_scan_time": "API scan time",
                    "api_recipe_id": "API recipe",
                    "api_defect_count": "API defect",

                    "offset_um": "offset",
                    "matched_pair_count": "same point",
                   
                },
            },


            "bpi_same_point_average": {
                "type": "density_avg",
                "tab_group": "bpi_same_point",
                "tab_order": 60,
                "tab_name": "同點平均值",

                "system_key": "bpi_same_point",

                "group_keys": [
                    "glass_side",
                    "model",
                    "offset_um",
                ],

                "metric_columns": [
                    "defect_cnt",
                    "total_glass_cnt",
                    "density",
                    "day_count",
                    "hour_count",
                ],

                "time_col": "scan_hour",
                "time_semantic": "scan_hour",
                "day_boundary": "07:30",

                # 同點平均值以 API 同點尺寸為主。
                "source_columns": {
                    "api_aoi": "api_aoi",
                    "glass_side": "glass_side",
                    "model": "model",
                    "recipe_id": "api_recipe_id",
                    "offset_um": "offset_um",

                    "defect_cnt": "matched_pair_count",
                    "total_glass_cnt": "__row_count__",

                    "small_defect_count": "matched_api_s_count",
                    "middle_defect_count": "matched_api_m_count",
                    "large_defect_count": "matched_api_l_count",
                    "over_defect_count": "matched_api_o_count",
                },

                "filter_item_coldict": {
                    "API AOI": {
                        "key": "api_aoi",
                        "values": self.common_aoi_values[:],
                        "cascade": True,
                    },
                    "glass_side": {
                        "key": "glass_side",
                        "values": self.common_glass_sides[:],
                        "cascade": True,
                    },
                    "Model": {
                        "key": "model",
                        "values": [],
                        "cascade": True,
                    },
                    "API recipe": {
                        "key": "recipe_id",
                        "values": [],
                        "cascade": True,
                    },
                    "Offset": {
                        "key": "offset_um",
                        "values": self.common_same_point_offsets[:],
                        "cascade": True,
                        "selection_mode": "single",
                        "default_value": 20,
                    },
                    "defect size": {
                        "key": "defect_size",
                        "values": self.common_defect_sizes[:],
                        "cascade": True,
                    },
                },

                "cascade_order": [
                    "api_aoi",
                    "glass_side",
                    "model",
                    "recipe_id",
                    "offset_um",
                    "defect_size",
                ],


                "recipe_defect_default_rules": [],

                "denominator_identity_cols": [
                    "glass_id",
                    "tab",
                    "bpi_aoi",
                    "bpi_recipe_id",
                    "bpi_scan_time",
                    "api_aoi",
                    "api_recipe_id",
                    "api_scan_time",
                ],

                "summary_row_identity_cols": [
                    "api_aoi",
                    "model",
                    "glass_side",
                    "recipe_id",
                ],

                "metric_definition": {
                    "rows": "count distinct(api_aoi, model, glass_side, api_recipe_id)",
                    "defect_cnt": "same_point_count = sum(matched_pair_count)",
                    "total_glass_cnt": "pair_count = count distinct glass pair under selected offset_um",
                    "density": "same_point_avg = same_point_count / pair_count",
                    "day_boundary": "07:30~next day 07:30",
                    "denominator_policy": "defect_size does not shrink pair_count; offset_um is single-select",
                },

                "summary_labels": {
                    "rows": {
                        "title": "Groups",
                        "subtitle": "api_aoi + model + side + recipe",
                    },
                    "defect_cnt": {
                        "title": "Same Point Count",
                        "subtitle": "sum matched_pair_count",
                    },
                    "total_glass_cnt": {
                        "title": "Pair Count",
                        "subtitle": "selected offset",
                    },
                    "density": {
                        "title": "Avg Same Point",
                        "subtitle": "same point / pair",
                    },
                },

                "table_columns": {
                    "glass_side": "side",
                    "model": "Model",
                    "offset_um": "offset",
                    "defect_cnt": "same point count",
                    "total_glass_cnt": "pair count",
                    "density": "avg same point / pair",
                    "day_count": "days",
                    "hour_count": "hours",
                },

                "download_columns": {
                    "glass_side": "side",
                    "model": "Model",
                    "offset_um": "offset",
                    "defect_cnt": "same point count",
                    "total_glass_cnt": "pair count",
                    "density": "avg same point / pair",
                    "day_count": "days",
                    "hour_count": "hours",
                },
            },
        }

    # =============================================================================
    # Front config
    # =============================================================================
    def _build_front_config(self) -> Dict[str, Any]:
        return {
            "SubTabGroups": self.tab_group_config,
            "SubTabsFilterDefaultDict": self.tab_filter_config,

            "bpiDensity": {
                "db_name": self.bpi_density_db_name,
                "summary_table_tpl": self.bpi_density_summary_table_tpl,
                "summary_tbn": self.bpi_density_summary_tbn,
                "summary_sql_cols": self.bpi_density_summary_sql_cols,
                "summary_api_cols": self.bpi_density_summary_api_cols,

                "default_spec_tbn": self.bpi_density_default_spec_tbn,
                "default_spec_sql_cols": self.bpi_density_default_spec_sql_cols,
                "default_spec_api_cols": self.bpi_density_default_spec_api_cols,

                "primary_group_cols": self.bpi_density_primary_group_cols,

                "chartKeyDict": self.bpi_density_chart_group_dict,

                # 保留錯字相容
                "filtetItemKeyDict": self.bpi_density_filter_item_coldict,
                "filterItemKeyDict": self.bpi_density_filter_item_coldict,

                "hourlyTable": self.bpi_density_chart_table_coldict,
                "hourlyTable_key_group": self.bpi_density_table_group_key_dict,
                "uniGlassInfo": self.bpi_density_uni_glass_row_info_dict,
            },

            "bpiSamePoint": {
                "db_name": self.bpi_same_point_db_name,
                "pair_table_tpl": self.bpi_same_point_pair_table_tpl,
                "offset_table_tpl": self.bpi_same_point_offset_table_tpl,
                "match_table_tpl": self.bpi_same_point_match_table_tpl,

                "pair_sql_cols": self.bpi_same_point_pair_sql_cols,
                "pair_api_cols": self.bpi_same_point_pair_api_cols,
                "offset_sql_cols": self.bpi_same_point_offset_sql_cols,
                "offset_api_cols": self.bpi_same_point_offset_api_cols,
                "match_sql_cols": self.bpi_same_point_match_sql_cols,
                "match_api_cols": self.bpi_same_point_match_api_cols,

                "default_spec_tbn": self.bpi_same_point_default_spec_tbn,
                "default_spec_sql_cols": self.bpi_same_point_default_spec_sql_cols,
                "default_spec_api_cols": self.bpi_same_point_default_spec_api_cols,

                # 重新產資料時，受影響的 pair/manual 保留母體 key。
                "affected_key_cols": [
                    "model",
                    "glass_side",
                    "glass_id",
                    "tab",
                    "api_aoi",
                    "api_recipe_id",
                ],

                # comment/action 保留 key。
                "manual_key_cols": [
                    "model",
                    "glass_side",
                    "glass_id",
                    "tab",
                    "api_aoi",
                    "api_recipe_id",
                ],

                # 給 editor.py 使用。
                # bpi_same_point 不使用 scan_hour / api_scan_time 當 comment/action key。
                "editor_match_keys": [
                    "model",
                    "glass_side",
                    "glass_id",
                    "tab",
                    "api_aoi",
                    "api_recipe_id",
                ],
                "editor_table_strategy": "source_table_or_scan_hour_month",
                "editor_time_key": "scan_hour",
                "editor_requires_time_key": False,
                "editor_col": "editor",

                # 給 map / 精準 row 使用，不是 editor key。
                "pair_key_cols": [
                    "model",
                    "glass_side",
                    "glass_id",
                    "tab",
                    "api_aoi",
                    "api_recipe_id",
                    "api_scan_time",
                ],

                "default_offset_field": "default_offset_um",
                "matched_points_field": "matched_points_json",

                "size_filter_logic": "bpi_or_api",
                "size_filter_fields": [
                    "bpi_defect_size",
                    "api_defect_size",
                ],

                "chartKeyDict": self.bpi_same_point_chart_group_dict,
                "hourlyTable": self.bpi_same_point_chart_table_coldict,
                "hourlyTable_key_group": self.bpi_same_point_table_group_key_dict,
                "filterItemKeyDict": self.bpi_same_point_filter_item_coldict,
                "defectMap": self.bpi_same_point_defect_map_config,
            },
        }
    # =============================================================================
    # Spec table
    # =============================================================================
    def _load_default_spec(
        self,
        *,
        handler,
        table_name: str,
        api_cols: List[str],
        sort_cols: List[str],
        dedup_cols: List[str],
    ) -> pd.DataFrame:
        try:
            rows = handler.get_rows(table_name, {"drop": "F"})
        except Exception:
            rows = []

        df = pd.DataFrame(rows)

        if not df.empty:
            for c in api_cols:
                if c not in df.columns:
                    df[c] = ""

            if "modify_time" in df.columns:
                df["modify_time"] = pd.to_datetime(df["modify_time"], errors="coerce")

            real_sort_cols = [c for c in sort_cols if c in df.columns]
            if real_sort_cols:
                df.sort_values(by=real_sort_cols, ascending=False, inplace=True)

            real_dedup_cols = [c for c in dedup_cols if c in df.columns]
            if real_dedup_cols:
                df = df.drop_duplicates(
                    subset=real_dedup_cols,
                    keep="first"
                ).reset_index(drop=True)

            df = df.fillna("")

            final_cols = [c for c in api_cols if c in df.columns]
            df = df[final_cols]
        else:
            df = pd.DataFrame(columns=api_cols)

        return df


    def bpi_density_spec_table_process(self, dbhandler):
        """
        只給 /bpi_density/reset_summary_filter 使用。
        只回傳 BPI Density default spec。
        """
        bpi_density_df = self._load_default_spec(
            handler=dbhandler,
            table_name=self.bpi_density_default_spec_tbn,
            api_cols=self.bpi_density_default_spec_api_cols,
            sort_cols=self.bpi_density_default_spec_api_cols,
            dedup_cols=[
                "model",
                "glass_type",
                "defect_size",
            ],
        )

        return {
            "bpi_density_default_spec": bpi_density_df.to_dict(orient="index")
        }


    def bpi_same_point_spec_table_process(self, dbhandler=None):
        """
        只給 /bpi_same_point/reset_filter 使用。
        只回傳 BPI Same Point default spec。
        """
        if dbhandler is None:
            dbhandler = MySQLConnet(self.bpi_same_point_db_name)

        bpi_same_point_df = self._load_default_spec(
            handler=dbhandler,
            table_name=self.bpi_same_point_default_spec_tbn,
            api_cols=self.bpi_same_point_default_spec_api_cols,
            sort_cols=self.bpi_same_point_default_spec_api_cols,
            dedup_cols=[
                "model",
                "glass_side",
                "defect_size",
            ],
        )

        return {
            "bpi_same_point_default_spec": bpi_same_point_df.to_dict(orient="index")
        }

if __name__ == "__main__":
    api_cfg = API_Config()
    print("BPI Density summary:", api_cfg.bpi_density_summary_tbn)
    print("BPI Same Point pair:", api_cfg.bpi_same_point_pair_tbn)
