import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
import numpy as np
import math
import warnings
import os 


INPUT_CSV_FILE_PATH = "points_data.csv"  # CSV file from S1, like 'SF_panorama_id.csv'
INPUT_BOUNDARY_SHP_PATH = "study_area_boundary.shp"  # Boundary shapefile , like 'SF_boundary.shp'

OUTPUT_DIRECTORY = "output_results" # folder name
OUTPUT_SAMPLED_POINTS_SHP_NAME = "YOUR_OWN_CITY_NAME_SVI_points_from_csv.shp" # replace with your own city name, like SF_SVI_points_from_csv.shp
OUTPUT_SAMPLED_POINTS_CSV_NAME_PREFIX = "YOUR_OWN_CITY_NAME_panorama_id" # replace with your own city name, like SF_panorama_id

YEAR_COLUMN_NAME = 'year'       
X_COORD_COLUMN_NAME = 'lon'     
Y_COORD_COLUMN_NAME = 'lat'      


INPUT_CSV_POINTS_CRS = "EPSG:4326"      
TARGET_PROCESSING_CRS = "EPSG:32610"    # YOUR FINAL TARGET CRS, like 'EPSG:32610' for SF

# YEAR RANGE
MIN_FILTER_YEAR = 2021
MAX_FILTER_YEAR = 2023


HEXAGON_RADIUS_METERS = 50



def reproject_gdf(gdf, target_crs_str, gdf_name="GeoDataFrame"):
    """将GeoDataFrame重投影到目标坐标系"""
    if gdf.crs is None:
        raise ValueError(f"{gdf_name} 没有定义CRS，无法继续。")

    try:
        target_crs_obj = gpd.CRS.from_user_input(target_crs_str)
    except Exception as e:
        raise ValueError(f"无法解析目标CRS字符串 '{target_crs_str}': {e}")

    # 避免不必要的重投影
    if gdf.crs.equals(target_crs_obj):
        print(f"{gdf_name} 已处于目标CRS {target_crs_obj.to_string()}。")
        return gdf.copy() # 返回副本

    source_epsg = gdf.crs.to_epsg() if hasattr(gdf.crs, 'to_epsg') and gdf.crs.is_projected == target_crs_obj.is_projected else None
    target_epsg = target_crs_obj.to_epsg() if hasattr(target_crs_obj, 'to_epsg') else None

    print(f"正在将 {gdf_name} 从 CRS '{gdf.crs.to_string()}' 重投影到 '{target_crs_obj.to_string()}'...")
    try:
        gdf_reprojected = gdf.to_crs(target_crs_obj)
    except Exception as e:
        raise Exception(f"重投影 {gdf_name} 到 {target_crs_obj.to_string()} 失败: {e}")
    return gdf_reprojected


def create_single_hexagon(center_x, center_y, radius):
    """创建一个以(center_x, center_y)为中心, 指定半径的六边形Polygon"""
    vertices = []
    for i in range(6):
        angle_rad = math.radians(60 * i + 30)
        x = center_x + radius * math.cos(angle_rad)
        y = center_y + radius * math.sin(angle_rad)
        vertices.append((x, y))
    return Polygon(vertices)

def generate_hexagon_grid(study_area_geometry, radius, crs):
    """在study_area_geometry的边界内生成六边形网格"""
    if study_area_geometry is None or study_area_geometry.is_empty:
        warnings.warn("研究区域几何对象为空，无法生成六边形网格。")
        return gpd.GeoDataFrame({'hex_id': [], 'geometry': []}, crs=crs)

    minx, miny, maxx, maxy = study_area_geometry.bounds
    
    R = radius
    dx = R * 1.5 
    dy = R * math.sqrt(3) / 2
    
    hexagons_list = []
    hex_ids_list = []
    current_id = 0
  
    buffer_dist = R * 2 

    y_start_iter = miny - buffer_dist
    row_idx = 0
    while y_start_iter < maxy + buffer_dist:
        y_center = y_start_iter
        x_start_offset = (row_idx % 2) * dx / 2 
        x_start_iter = minx - buffer_dist + x_start_offset
        
        while x_start_iter < maxx + buffer_dist:
            x_center = x_start_iter
            hexagon = create_single_hexagon(x_center, y_center, R)
            hexagons_list.append(hexagon)
            hex_ids_list.append(current_id)
            current_id += 1
            x_start_iter += dx
        y_start_iter += dy
        row_idx += 1
        
    if not hexagons_list:
        warnings.warn("未能生成任何六边形。请检查研究区域边界和半径。")
        return gpd.GeoDataFrame({'hex_id': [], 'geometry': []}, crs=crs)

    hexagon_grid_gdf = gpd.GeoDataFrame({'hex_id': hex_ids_list, 'geometry': hexagons_list}, crs=crs)
    
    print(f"正在将 {len(hexagon_grid_gdf)} 个生成的六边形裁剪到研究区域边界...")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning) 
        # 确保 study_area_geometry 是单个有效的几何对象进行裁剪
        if isinstance(study_area_geometry, (gpd.GeoDataFrame, gpd.GeoSeries)):
            clipping_mask = unary_union(study_area_geometry.geometry)
        else: # 假定是单个Shapely几何对象
            clipping_mask = study_area_geometry
        
        if clipping_mask is None or clipping_mask.is_empty:
            warnings.warn("裁剪掩膜无效或为空，返回未裁剪的六边形网格。")
            return hexagon_grid_gdf # 或者返回错误/空GDF

        clipped_hex_grid = gpd.clip(hexagon_grid_gdf, clipping_mask)

    clipped_hex_grid = clipped_hex_grid[~clipped_hex_grid.is_empty].reset_index(drop=True)
    if not clipped_hex_grid.empty:
        clipped_hex_grid['hex_id'] = range(len(clipped_hex_grid))
    return clipped_hex_grid


def filter_points_by_hexagon(sampling_points_gdf, hexagon_grid_gdf_input):
    """筛选采样点，确保每个六边形只有一个点 (距离六边形中心最近)"""
    if sampling_points_gdf.empty or hexagon_grid_gdf_input.empty:
        warnings.warn("输入的点或六边形为空。返回空的GeoDataFrame。")
        return gpd.GeoDataFrame(columns=sampling_points_gdf.columns if sampling_points_gdf is not None else None, 
                                crs=sampling_points_gdf.crs if sampling_points_gdf is not None and hasattr(sampling_points_gdf, 'crs') else None)


    hexagon_grid_gdf = hexagon_grid_gdf_input.copy()
    # 确保 hex_id 存在且唯一
    if 'hex_id' not in hexagon_grid_gdf.columns or not hexagon_grid_gdf['hex_id'].is_unique:
        warnings.warn("hexagon_grid_gdf 中的 'hex_id' 不存在或不唯一。将重新分配。")
        hexagon_grid_gdf = hexagon_grid_gdf.reset_index(drop=True) # 确保索引是唯一的
        hexagon_grid_gdf['hex_id'] = hexagon_grid_gdf.index


    if sampling_points_gdf.crs != hexagon_grid_gdf.crs:
        print(f"为空间连接对齐CRS：将采样点从 {sampling_points_gdf.crs} 重投影到 {hexagon_grid_gdf.crs}")
        sampling_points_gdf = sampling_points_gdf.to_crs(hexagon_grid_gdf.crs)

    # 使用 'intersects' predicate 通常比 'within' 更稳健，特别是对于边界情况
    points_in_hexagons = gpd.sjoin(sampling_points_gdf, hexagon_grid_gdf, how="inner", predicate="intersects")

    if points_in_hexagons.empty:
        print("没有采样点与任何六边形相交。")
        return gpd.GeoDataFrame(columns=sampling_points_gdf.columns, crs=sampling_points_gdf.crs)

    # 清理 sjoin 可能产生的列名冲突
    if 'hex_id_left' in points_in_hexagons.columns:
        points_in_hexagons = points_in_hexagons.drop(columns=['hex_id_left'])
    if 'hex_id_right' in points_in_hexagons.columns:
        points_in_hexagons = points_in_hexagons.rename(columns={'hex_id_right':'hex_id'})
    
    # 合并六边形几何，确保使用唯一的 hex_id
    points_in_hexagons = points_in_hexagons.merge(
        hexagon_grid_gdf[['hex_id', 'geometry']].rename(columns={'geometry': 'hexagon_geometry'}),
        on='hex_id',
        how='left' # 使用 left join 以防万一有 hex_id 匹配问题
    )
    
    points_in_hexagons = points_in_hexagons[points_in_hexagons['hexagon_geometry'].notna()]
    if points_in_hexagons.empty:
        print("在合并六边形几何后没有有效的点了。")
        return gpd.GeoDataFrame(columns=sampling_points_gdf.columns, crs=sampling_points_gdf.crs)


    points_in_hexagons['hexagon_centroid'] = points_in_hexagons['hexagon_geometry'].apply(lambda geom: geom.centroid if geom and not geom.is_empty else None)
    points_in_hexagons = points_in_hexagons[points_in_hexagons['hexagon_centroid'].notna()]

    if points_in_hexagons.empty:
        print("在计算六边形质心后没有有效的点了。")
        return gpd.GeoDataFrame(columns=sampling_points_gdf.columns, crs=sampling_points_gdf.crs)

    points_in_hexagons['distance_to_centroid'] = points_in_hexagons.apply(
        lambda row: row.geometry.distance(row['hexagon_centroid']), axis=1
    )

    # idxmin() 返回每个组中最小值对应的索引 (points_in_hexagons 的索引)
    idx_min_dist = points_in_hexagons.groupby('hex_id')['distance_to_centroid'].idxmin()
    selected_rows_gdf = points_in_hexagons.loc[idx_min_dist]

    # 保留原始采样点的列，并确保几何列设置正确
    original_point_columns = [col for col in sampling_points_gdf.columns if col != 'geometry']
    final_columns = ['geometry'] + original_point_columns
    
    # 确保所有期望的列都存在于 selected_rows_gdf 中
    columns_to_select = [col for col in final_columns if col in selected_rows_gdf.columns]
    
    final_svi_gdf = selected_rows_gdf[columns_to_select].copy()
    final_svi_gdf = final_svi_gdf.set_geometry("geometry").set_crs(sampling_points_gdf.crs, allow_override=True)
    return final_svi_gdf


if __name__ == "__main__":
    print("开始从CSV进行SVI采样流程...")

    # 创建输出目录 (如果不存在)
    if not os.path.exists(OUTPUT_DIRECTORY):
        os.makedirs(OUTPUT_DIRECTORY)
        print(f"已创建输出目录: {OUTPUT_DIRECTORY}")

    # 1. 加载边界数据并准备研究区域几何对象
    print(f"正在加载边界数据: {INPUT_BOUNDARY_SHP_PATH}...")
    try:
        boundary_gdf = gpd.read_file(INPUT_BOUNDARY_SHP_PATH)
    except Exception as e:
        print(f"错误：无法读取边界文件 {INPUT_BOUNDARY_SHP_PATH}。请检查文件路径和完整性。错误信息: {e}")
        exit()
        
    boundary_gdf = reproject_gdf(boundary_gdf, TARGET_PROCESSING_CRS, "边界GDF")
    study_area_geometry = unary_union(boundary_gdf.geometry) 

    if study_area_geometry is None or study_area_geometry.is_empty:
        print(f"错误：研究区域几何对象无效或为空。请检查边界文件 {INPUT_BOUNDARY_SHP_PATH}。")
        exit()

    # 2. 加载CSV数据
    print(f"正在加载CSV数据: {INPUT_CSV_FILE_PATH}...")
    try:
        points_df = pd.read_csv(INPUT_CSV_FILE_PATH)
    except FileNotFoundError:
        print(f"错误：找不到CSV文件 {INPUT_CSV_FILE_PATH}。请检查文件路径。")
        exit()
    except Exception as e:
        print(f"错误：读取CSV文件 {INPUT_CSV_FILE_PATH} 时出错: {e}")
        exit()

    # 3. 按年份筛选CSV数据
    print(f"按年份 ({YEAR_COLUMN_NAME} 列) 筛选数据 ({MIN_FILTER_YEAR}-{MAX_FILTER_YEAR})...")
    if YEAR_COLUMN_NAME not in points_df.columns:
        print(f"错误：CSV文件中找不到年份列 '{YEAR_COLUMN_NAME}'。")
        exit()
    
    try:
        # 确保年份列是数值或可以安全转换为数值
        points_df[YEAR_COLUMN_NAME] = pd.to_numeric(points_df[YEAR_COLUMN_NAME], errors='coerce')
        # 移除转换后为NaT/NaN的行 (如果errors='coerce')
        points_df.dropna(subset=[YEAR_COLUMN_NAME], inplace=True) 
        points_df[YEAR_COLUMN_NAME] = points_df[YEAR_COLUMN_NAME].astype(int) # 转换为整数年份

        points_df_filtered_year = points_df[
            (points_df[YEAR_COLUMN_NAME] >= MIN_FILTER_YEAR) & (points_df[YEAR_COLUMN_NAME] <= MAX_FILTER_YEAR)
        ].copy()
    except Exception as e:
        print(f"错误：处理或筛选年份列 '{YEAR_COLUMN_NAME}' 时出错: {e}")
        exit()

    if points_df_filtered_year.empty:
        print(f"在年份范围 {MIN_FILTER_YEAR}-{MAX_FILTER_YEAR} 内按年份筛选后没有数据。")
        exit()
    print(f"年份筛选后剩余 {len(points_df_filtered_year)} 个点。")

    # 4. 将筛选后的Pandas DataFrame转换为GeoDataFrame
    print(f"从CSV坐标 ({X_COORD_COLUMN_NAME}, {Y_COORD_COLUMN_NAME}) 创建GeoDataFrame...")
    if X_COORD_COLUMN_NAME not in points_df_filtered_year.columns or Y_COORD_COLUMN_NAME not in points_df_filtered_year.columns:
        print(f"错误：CSV文件中找不到坐标列 '{X_COORD_COLUMN_NAME}' 或 '{Y_COORD_COLUMN_NAME}'。")
        exit()
    
    points_df_filtered_year.dropna(subset=[X_COORD_COLUMN_NAME, Y_COORD_COLUMN_NAME], inplace=True)
    if points_df_filtered_year.empty:
        print("移除空坐标后没有数据。")
        exit()

    try:
        # 确保坐标是数值类型
        points_df_filtered_year[X_COORD_COLUMN_NAME] = pd.to_numeric(points_df_filtered_year[X_COORD_COLUMN_NAME], errors='coerce')
        points_df_filtered_year[Y_COORD_COLUMN_NAME] = pd.to_numeric(points_df_filtered_year[Y_COORD_COLUMN_NAME], errors='coerce')
        points_df_filtered_year.dropna(subset=[X_COORD_COLUMN_NAME, Y_COORD_COLUMN_NAME], inplace=True) # 再次移除转换失败的行

        geometry = [Point(xy) for xy in zip(points_df_filtered_year[X_COORD_COLUMN_NAME], points_df_filtered_year[Y_COORD_COLUMN_NAME])]
        initial_points_gdf = gpd.GeoDataFrame(points_df_filtered_year, geometry=geometry, crs=INPUT_CSV_POINTS_CRS)
    except Exception as e:
        print(f"错误：从CSV坐标创建GeoDataFrame时出错: {e}")
        exit()

    # 5. 重投影点数据到目标CRS并裁剪到边界内
    initial_points_gdf = reproject_gdf(initial_points_gdf, TARGET_PROCESSING_CRS, "初始点GDF")
    
    print("将初始点裁剪到研究区域边界内...")
    boundary_for_sjoin = gpd.GeoDataFrame(geometry=[study_area_geometry], crs=TARGET_PROCESSING_CRS)
    initial_points_in_boundary = gpd.sjoin(initial_points_gdf, boundary_for_sjoin, how="inner", predicate="intersects") # 使用 intersects 更稳健
    
    # sjoin 后清理 'index_right' 列
    if 'index_right' in initial_points_in_boundary.columns:
        initial_points_in_boundary = initial_points_in_boundary.drop(columns=['index_right'])


    if initial_points_in_boundary.empty:
        print("裁剪到边界后没有点数据。")
        exit()
    print(f"边界内共有 {len(initial_points_in_boundary)} 个点用于后续处理。")

    # 6. 生成六边形网格
    print(f"正在生成六边形网格 (半径: {HEXAGON_RADIUS_METERS}m)...")
    hexagon_grid_gdf = generate_hexagon_grid(study_area_geometry, HEXAGON_RADIUS_METERS, crs=TARGET_PROCESSING_CRS)
    if hexagon_grid_gdf.empty:
        print("未能生成六边形网格。")
        exit()
    print(f"在研究区域内生成了 {len(hexagon_grid_gdf)} 个六边形。")

    # 7. 应用筛选方法：每个六边形一个点
    print("正在筛选点，确保每个六边形一个点 (距离六边形中心最近)...")
    final_svi_points_gdf = filter_points_by_hexagon(initial_points_in_boundary, hexagon_grid_gdf)
    print(f"最终筛选出 {len(final_svi_points_gdf)} 个SVI采样点。")

    # 8. 保存输出
    if not final_svi_points_gdf.empty:
        # 构建输出文件路径
        output_shp_path = os.path.join(OUTPUT_DIRECTORY, OUTPUT_SAMPLED_POINTS_SHP_NAME)
        
        try:
            final_svi_points_gdf.to_file(output_shp_path, driver="ESRI Shapefile")
            print(f"最终SVI采样点已保存到 Shapefile: {output_shp_path}")
        except Exception as e:
            print(f"保存为Shapefile时出错: {e}")
            output_geojson_path = os.path.join(OUTPUT_DIRECTORY, OUTPUT_SAMPLED_POINTS_SHP_NAME.replace(".shp", ".geojson"))
            try:
                final_svi_points_gdf.to_file(output_geojson_path, driver="GeoJSON")
                print(f"已尝试将结果保存为GeoJSON: {output_geojson_path}")
            except Exception as e_geojson:
                print(f"保存为GeoJSON也失败: {e_geojson}")

        print(f"正在将筛选后的点保存到新的CSV文件...")
        try:
            year_range_str = f"{MIN_FILTER_YEAR}-{MAX_FILTER_YEAR}"
            output_csv_filename = f"{OUTPUT_SAMPLED_POINTS_CSV_NAME_PREFIX}_{year_range_str}.csv"
            output_csv_path = os.path.join(OUTPUT_DIRECTORY, output_csv_filename)
            
            df_to_save_csv = final_svi_points_gdf.copy()

            if 'geometry' in df_to_save_csv.columns and isinstance(df_to_save_csv, gpd.GeoDataFrame):
                # 保存投影坐标的X, Y值
                df_to_save_csv['coord_X_projected'] = df_to_save_csv.geometry.x
                df_to_save_csv['coord_Y_projected'] = df_to_save_csv.geometry.y
                
                df_for_csv_export = pd.DataFrame(df_to_save_csv.drop(columns=['geometry']))
            else:
                warnings.warn("警告：'geometry' 列未找到或 df_to_save_csv 不是 GeoDataFrame。CSV将不包含提取的X,Y坐标。")
                df_for_csv_export = pd.DataFrame(df_to_save_csv)

            df_for_csv_export.to_csv(output_csv_path, index=False, encoding='utf-8')
            print(f"筛选后的点已成功保存到CSV文件: {output_csv_path}")

        except Exception as e_csv:
            print(f"保存到新的CSV文件时发生错误: {e_csv}")
    else:
        print("没有最终的SVI采样点可供保存。")

    print("SVI采样流程 (从CSV) 完成。")