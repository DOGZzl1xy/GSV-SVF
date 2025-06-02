# GSV-SVF

This work is based on the prior work on SVF. \
Get street view code is based on Shengao Yi's work https://github.com/ShengaoYi/Google-StreetView-Downloader and  robolyst's work https://github.com/robolyst/streetview. \
The segment code is based on Ito's work https://github.com/koito19960406/ZenSVI. \
The segment method is developed by Meta on https://github.com/facebookresearch/Mask2Former. \
The fisheye transfer method is developed by Xiaojiang Li's paper https://doi.org/10.1007/978-3-319-57336-6_24.  

## Project structure

GSV/
- GoogleStreetViews/
  - {Cityname}_year/             # Final output directory after S2, like 'SF_2023'
  - {Cityname}_year_fisheye_512/ # Folder contains fisheye image, after S4a Step 2
  - {Cityname}_year_segment/     # Folder contains segmented image, after S3
  - fisheye_result_YEAR.csv      # CSV file for final result, after S4a Step 3, like 'fisheye_result_2023'
- pid_dir/
  - {city_name}_panorama\_{year}.csv    # like 'SF_panorama_2023.csv'
- UserAgent.csv                         #Your own Google Maps API, no less than 5 apis
- {Cityname}_pid_got.csv                #like 'SF_pid_got.csv', from S1-Step2.2, NO USE
- {Cityname}_download.csv               #like 'SF_download.csv', from S2, NO USE
- {Cityname}_road_path_index.csv        #like 'SF_road_path_index.csv', from S1-Step2.1
- groundingdino_swint_ogc.pth           #Model weight for segment in S3

