#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
測試腳本：從 .defect 檔案提取目標資料
提取欄位：StartDate、MachineID、Device、LotID、GlassID、MaxDefsEstimate、DefectID、Coordinate_X、Coordinate_Y、AreaSize
每個 Defect 產生一筆資料
"""

import os
import json
import csv
import xmltodict
from pathlib import Path
from datetime import datetime


class DefectDataExtractor:
    """缺陷資料提取器"""
    
    def __init__(self, source_dir="rtms", output_dir="output", starttime=None, endtime=None):
        """
        初始化提取器
        :param source_dir: 來源 rtms 資料夾
        :param output_dir: 輸出資料夾
        :param starttime: 開始時間 (datetime 物件或 'YYYY-MM-DD HH:MM:SS' 字串，None 表示不限制)
        :param endtime: 結束時間 (datetime 物件或 'YYYY-MM-DD HH:MM:SS' 字串，None 表示不限制)
        """
        self.source_dir = source_dir
        self.output_dir = output_dir
        self.extracted_data = []
        
        # 轉換時間參數
        self.starttime = self._parse_datetime(starttime) if starttime else None
        self.endtime = self._parse_datetime(endtime) if endtime else None
        
        if self.starttime and self.endtime and self.starttime > self.endtime:
            print("警告: starttime 晚於 endtime，將互換")
            self.starttime, self.endtime = self.endtime, self.starttime
        
        self.create_output_dir()
    
    def _parse_datetime(self, dt):
        """
        解析時間字串或 datetime 物件
        :param dt: datetime 物件或 'YYYY-MM-DD HH:MM:SS' 字串
        :return: datetime 物件
        """
        if isinstance(dt, datetime):
            return dt
        elif isinstance(dt, str):
            try:
                return datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                print(f"時間格式錯誤: {dt}，應為 'YYYY-MM-DD HH:MM:SS'")
                return None
        return None
    
    def is_file_in_time_range(self, file_path):
        """
        檢查檔案修改時間是否在指定範圍內
        :param file_path: 檔案路徑
        :return: True 如果檔案在時間範圍內，False 否則
        """
        if not self.starttime and not self.endtime:
            return True
        
        try:
            # 獲取檔案修改時間戳
            mtime_timestamp = os.path.getmtime(file_path)
            file_mtime = datetime.fromtimestamp(mtime_timestamp)
            
            # 檢查時間範圍
            if self.starttime and file_mtime < self.starttime:
                return False
            if self.endtime and file_mtime > self.endtime:
                return False
            
            return True
        except Exception as e:
            print(f"無法檢查檔案修改時間: {file_path}, 錯誤: {e}")
            return False
    
    def create_output_dir(self):
        """建立輸出資料夾"""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
    
    def read_xml_file(self, file_path):
        """
        讀取 XML 檔案
        :param file_path: 檔案路徑
        :return: 解析後的字典
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            data_dict = xmltodict.parse(content)
            return data_dict
        except Exception as e:
            print(f"讀取或解析 XML 失敗: {file_path}, 錯誤: {e}")
            return None
    
    def extract_cst_flowindex_from_filename(self, filename):
        """
        從檔案名稱提取 CST 和 FLOWINDEX
        :param filename: 檔案名稱
        :return: (CST, FLOWINDEX)
        """
        try:
            parts = filename.split('.')
            # filedetail[3][:-2] = CST (去掉最後2個字符)
            # filedetail[5] = FLOWINDEX
            cst = parts[3]
            flowindex = parts[5]
            return cst, flowindex
        except Exception as e:
            print(f"提取 CST/FLOWINDEX 失敗: {e}")
            return 'N/A', 'N/A'
    
    def extract_glass_type_from_filename(self, filename):
        """
        從檔案名稱提取 glass_type (根據 RECIPE)
        邏輯參考 read_aoi300.py
        :param filename: 檔案名稱
        :return: glass_type
        """
        try:
            parts = filename.split('.')
            recipe = parts[2]
            
            # 根據 RECIPE 判斷 GLASSTYPE
            if recipe == 'CELL-ITO':
                glass_type = 'ITO'
            elif recipe == 'CELL-ITO_20230823':
                glass_type = 'ITO'
            elif recipe == 'C-API':
                glass_type = 'PASS'
            elif recipe == 'T-API':
                glass_type = 'PASS'
            else:
                # 其他情況：從 RECIPE 中分解
                recipe_parts = recipe.split('-')
                if len(recipe_parts) > 1:
                    glass_type = recipe_parts[1]
                    
                    # 轉換縮寫
                    if glass_type == 'T':
                        glass_type = 'TFT'
                    elif glass_type == 'C':
                        glass_type = 'CF'
                    elif glass_type == 'TD':
                        glass_type = 'ITO'
                    
                    # 檢查是否為 ITO
                    if glass_type == 'T' and len(recipe_parts) > 2 and recipe_parts[2] == 'ITO':
                        glass_type = 'ITO'
                else:
                    glass_type = 'Unknown'
            
            return glass_type
        except Exception as e:
            print(f"提取 glass_type 失敗: {e}")
            return 'Unknown'
    
    def extract_macro_image_paths(self, macro_filename):
        """
        從 macro 檔案提取 4 個 ImgName
        :param macro_filename: macro 檔案名稱（去掉 .defect 後替換為 .macro）
        :return: ImgName 列表，最多 4 個
        """
        macro_path = os.path.join(self.source_dir, macro_filename)
        
        if not os.path.exists(macro_path):
            print(f"  警告: macro 檔案不存在: {macro_path}")
            return []
        
        try:
            macro_data = self.read_xml_file(macro_path)
            if not macro_data:
                return []
            
            # 提取 Images 下的 GlassImage 列表
            images_section = macro_data.get('Body', {}).get('MacroInspection', {}).get('Images', {})
            glass_images = images_section.get('GlassImage', [])
            
            # 確保 glass_images 是列表
            if isinstance(glass_images, dict):
                glass_images = [glass_images]
            
            # 提取 ImgName，最多 4 個
            img_names = []
            for glass_image in glass_images[:4]:
                img_name = glass_image.get('ImgName', '')
                if img_name:
                    img_names.append(img_name)
            
            return img_names
        except Exception as e:
            print(f"  提取 macro 檔案失敗: {e}")
            return []
    
    def extract_defect_file(self, file_path, filename):
        """
        從 .defect 檔案提取缺陷資料
        :param file_path: 檔案路徑
        :param filename: 檔案名稱
        :return: 提取的資料列表，以及基礎資訊字典
        """
        data = self.read_xml_file(file_path)
        if not data:
            return [], {}
        
        records = []
        base_info = {}
        
        try:
            # 提取 InspectionInfo
            inspection_info = data.get('Body', {}).get('InspectionInfo', {})
            
            start_date = inspection_info.get('StartDate', 'N/A')
            machine_id = inspection_info.get('MachineID', 'N/A')
            device = inspection_info.get('Device', 'N/A')
            lot_id = inspection_info.get('LotID', 'N/A')
            glass_id = inspection_info.get('GlassID', 'N/A')
            max_defs_estimate = inspection_info.get('MaxDefsEstimate', '0')
            layer = inspection_info.get('Layer', 'N/A')
            
            # 從檔案名稱提取 CST 和 FLOWINDEX
            cst, flowindex = self.extract_cst_flowindex_from_filename(filename)
            
            # 從檔案名稱提取 glass_type
            glass_type = self.extract_glass_type_from_filename(filename)
            
            # 保存基礎信息供後續使用
            base_info = {
                'start_date': start_date,
                'machine_id': machine_id,
                'device': device,
                'lot_id': lot_id,
                'glass_id': glass_id,
                'glass_type': glass_type,
                'max_defs_estimate': max_defs_estimate,
                'cst': cst,
                'flowindex': flowindex,
                'layer': layer
            }
            
            # 提取 Defects
            defects_section = data.get('Body', {}).get('Defects', {})

            if defects_section != None:
                defects = defects_section.get('Defect', [])
                
                # 確保 defects 是列表（即使只有一個缺陷也要轉為列表）
                if isinstance(defects, dict):
                    defects = [defects]
                
                # 為每個缺陷建立一筆記錄
                for defect in defects:
                    coordinate = defect.get('Coordinate', {})
                    coord_x = coordinate.get('X', 'N/A')
                    coord_y = coordinate.get('Y', 'N/A')
                    area_size = defect.get('AreaSize', 'N/A')
                    defect_id = defect.get('DefectID', 'N/A')
                    
                    # 從 JudgeDefect 提取 SizeClass
                    judge_defect = defect.get('JudgeDefect', {})
                    size_class = judge_defect.get('SizeClass', 'N/A')
                    
                    # 提取 RepID (芯片序號)
                    rep_id = defect.get('RepID', 'N/A')
                    
                    # 組建 chip_id = GlassID + RepID
                    chip_id = glass_id + str(rep_id) if rep_id != 'N/A' else 'N/A'
                    
                    # 提取影像檔案名稱
                    images = defect.get('Images', {})
                    image = images.get('Image', {})
                    if str(type(image)) == "<class 'list'>":
                        image_file = image[0].get('file', 'N/A')
                    else:
                        image_file = image.get('file', 'N/A')
                    
                    # 組建 image_path
                    image_path = f"http://10.97.139.98:1454/{machine_id}/{cst}/{glass_id}/PCS1/{flowindex}/CaptureImage/small/{image_file}"
                    
                    record = {
                        'scan_time': str((datetime.fromtimestamp(int(start_date))).strftime("%Y-%m-%d %H:%M:%S")),
                        'line_id': '',
                        'aoi': machine_id,
                        'model': layer,
                        'glass_type': glass_type,
                        'recipe_id': device,
                        'glass_id': glass_id,
                        'x': str(round(float(coord_x)*1000)),
                        'y': str(round(1500000-float(coord_y)*1000)),
                        'defect_size': str(round(float(area_size))),
                        'size_class': size_class,
                        'ai_code_1': '',
                        'chip_name': chip_id,
                        'pi_time': '',
                        'pic_path': image_path,
                        'cst_id': lot_id,
                        'defect_count': max_defs_estimate,
                        'defect_id': defect_id
                    }
                    records.append(record)
            
        except Exception as e:
            print(f"提取資料失敗: {e}")
        
        return records, base_info
    
    def process_all_defect_files(self):
        """
        處理所有 .defect 檔案
        """
        if not os.path.exists(self.source_dir):
            print(f"✗ rtms 資料夾不存在: {self.source_dir}")
            return
        
        files = os.listdir(self.source_dir)
        defect_files = [f for f in files if f.endswith('.defect')]
        
        if not defect_files:
            print("✗ 找不到 .defect 檔案")
            return
        
        # 應用時間篩選
        filtered_files = []
        for file_name in defect_files:
            file_path = os.path.join(self.source_dir, file_name)
            if self.is_file_in_time_range(file_path):
                filtered_files.append(file_name)
        
        print(f"找到 {len(defect_files)} 個 .defect 檔案")
        if self.starttime or self.endtime:
            time_range_str = ""
            if self.starttime:
                time_range_str += f"從 {self.starttime.strftime('%Y-%m-%d %H:%M:%S')} "
            if self.endtime:
                time_range_str += f"到 {self.endtime.strftime('%Y-%m-%d %H:%M:%S')}"
            print(f"時間篩選範圍: {time_range_str}")
            print(f"篩選後: {len(filtered_files)} 個檔案符合條件\n")
        else:
            print()
        
        if not filtered_files:
            print("✗ 沒有檔案符合時間範圍條件")
            return
        
        for file_name in filtered_files:
            file_path = os.path.join(self.source_dir, file_name)
            mtime_timestamp = os.path.getmtime(file_path)
            mtime = datetime.fromtimestamp(mtime_timestamp).strftime('%Y-%m-%d %H:%M:%S')
            print(f"處理: {file_name} (修改時間: {mtime})")
            
            # 提取缺陷資料和基礎資訊
            records, base_info = self.extract_defect_file(file_path, file_name)
            print(f"  ✓ 提取了 {len(records)} 筆缺陷資料")
            
            self.extracted_data.extend(records)
            
            # 提取宏觀影像資料
            macro_filename = file_name.replace('.defect', '.macro')
            img_names = self.extract_macro_image_paths(macro_filename)
            
            if img_names:
                print(f"  ✓ 提取了 {len(img_names)} 筆宏觀影像資料")
                
                # 轉換 scan_time 為標準日期格式
                try:
                    start_date_timestamp = int(base_info.get('start_date', 0))
                    scan_time_formatted = datetime.fromtimestamp(start_date_timestamp).strftime("%Y-%m-%d %H:%M:%S")
                except:
                    scan_time_formatted = base_info.get('start_date', 'N/A')
                
                # 取最後一筆缺陷記錄的 defect_count
                last_defect_count = records[-1]['defect_count'] if records else '0'
                
                # 為每個宏觀影像建立一筆記錄
                for img_name in img_names:
                    
                    macro_record = {
                        'scan_time': scan_time_formatted,
                        'line_id': '',
                        'aoi': base_info.get('machine_id', 'N/A'),
                        'model': base_info.get('layer', 'N/A'),
                        'glass_type': base_info.get('glass_type', 'N/A'),
                        'recipe_id': base_info.get('device', 'N/A'),
                        'glass_id': base_info.get('glass_id', 'N/A'),
                        'x': '0',
                        'y': '0',
                        'defect_size': '0',
                        'size_class': '',
                        'ai_code_1': '',
                        'chip_name': base_info.get('glass_id', 'N/A')+"0",
                        'pi_time': '',
                        'pic_path': f"http://10.97.139.98:1454/{base_info.get('machine_id', 'N/A')}/{base_info.get('lot_id', 'N/A')}/{base_info.get('glass_id', 'N/A')}/PCS1/{base_info.get('flowindex', 'N/A')}/Map/{img_name}",
                        'cst_id': base_info.get('lot_id', 'N/A'),
                        'defect_count': last_defect_count,
                        'defect_id': '0'
                    }
                    self.extracted_data.append(macro_record)
            
            print()

    
    def save_as_json(self, output_filename="defects_extracted.json"):
        """
        保存為 JSON 檔案
        :param output_filename: 輸出檔案名稱
        """
        output_path = os.path.join(self.output_dir, output_filename)
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(self.extracted_data, f, ensure_ascii=False, indent=2)
            print(f"✓ 已保存 JSON: {output_path}")
        except Exception as e:
            print(f"保存 JSON 失敗: {e}")
    
    # def save_as_csv(self, output_filename="defects_extracted.csv"):
    #     """
    #     保存為 CSV 檔案
    #     :param output_filename: 輸出檔案名稱
    #     """
    #     if not self.extracted_data:
    #         print("沒有資料可保存")
    #         return
        
    #     output_path = os.path.join(self.output_dir, output_filename)
        
    #     try:
    #         fieldnames = [
    #             'StartDate', 'MachineID', 'Device', 'LotID', 'GlassID', 'glass_type', 'chip_id',
    #             'MaxDefsEstimate', 'DefectID', 'Coordinate_X', 'Coordinate_Y', 'AreaSize', 'image_path'
    #         ]
            
    #         with open(output_path, 'w', newline='', encoding='utf-8') as f:
    #             writer = csv.DictWriter(f, fieldnames=fieldnames)
    #             writer.writeheader()
    #             writer.writerows(self.extracted_data)
            
    #         print(f"✓ 已保存 CSV: {output_path}")
    #     except Exception as e:
    #         print(f"保存 CSV 失敗: {e}")
    
    def display_summary(self):
        """
        顯示摘要資訊
        """
        print("\n" + "=" * 70)
        print("資料提取摘要")
        print("=" * 70)
        print(f"總計提取的記錄數: {len(self.extracted_data)}")
        
        if self.extracted_data:
            print(f"\n前 3 筆記錄:")
            for i, record in enumerate(self.extracted_data[:3], 1):
                print(f"\n記錄 {i}:")
                for key, value in record.items():
                    print(f"  {key}: {value}")
        
        print("\n" + "=" * 70)


def main():
    """主程式"""
    print("=" * 70)
    print("RTMS 缺陷資料提取工具")
    print("=" * 70 + "\n")
    
    # ========== 設定時間範圍 ==========
    # 設定開始時間 (None 表示不限制)
    # 範例: starttime = '2026-01-22 13:00:00'
    starttime = None
    
    # 設定結束時間 (None 表示不限制)
    # 範例: endtime = '2026-01-22 14:00:00'
    endtime = None
    
    # ================================
    
    # 建立提取器
    extractor = DefectDataExtractor(
        source_dir="//10.97.136.13/rtms", 
        # source_dir="sample", 
        output_dir="output",
        starttime=starttime,
        endtime=endtime
    )
    
    # 處理所有 .defect 檔案
    extractor.process_all_defect_files()
    
    # 保存結果
    if extractor.extracted_data:
        extractor.save_as_json() #儲存JSON
        # extractor.display_summary() #顯示前幾筆資料
        if extractor.extracted_data:
            print(f"\n前 5 筆記錄:")
            for i, record in enumerate(extractor.extracted_data[:5], 1):
                print(f"\n記錄 {i}:")
                for key, value in record.items():
                    print(f"  {key}: {value}")
        print("\n" + "=" * 70)
    else:
        print("未成功提取任何資料")


if __name__ == "__main__":
    main()
