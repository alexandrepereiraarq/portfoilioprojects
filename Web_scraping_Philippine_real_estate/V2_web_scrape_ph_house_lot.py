# code from https://github.com/arl7d/portfoilioprojects/blob/main/Web_scraping_Philippine_real_estate/V2_web_scrape_ph_house_lot.py
# data scrapped from https://www.lamudi.com.ph/

from bs4 import BeautifulSoup
import requests
import unicodedata
import lxml 
from lxml import etree

import geopandas as gpd
import pandas as pd

# function below taken from stack overflow to convert latin n to english n
def strip_accents(text):
    return ''.join(char for char in
                   unicodedata.normalize('NFKD', text)
                   if unicodedata.category(char) != 'Mn')

# main routine to sift through pages and take real estate info then load it into dataframe
# create empty dict as a container for our data later on
real_estate_dict = {}
# initialize page as zero
page = 0
max_page = 50

while page in range(0,max_page):
    page += 1
    html_text = requests.get(f'https://www.lamudi.com.ph/buy/?page={page}').text
    soup = BeautifulSoup(html_text,'lxml')   #(html_text, 'lxml') html.parser
    all_info = soup.find_all('div', class_='ListingCell-AllInfo ListingUnit')
    for i in range(len(all_info)):
        info = all_info[i]
        header = info.find('h3', class_='ListingCell-KeyInfo-title').text.strip()
        #print('begin add: ', header) # used for testing/debugging
        location = info.find('span', class_='ListingCell-KeyInfo-address-text').text.strip()
        try:
            price = info.find('span', class_='PriceSection-FirstPrice').text.strip()
        except AttributeError:
            price ="na"
        try:
            bedrooms = '' 
            bath = ''
            floor_area = ''
            # the xml coding changed since the initial scrapping, so we need to adjust the code
            amenities = info.find_all('span', class_='KeyInformation-value_v2 KeyInformation-amenities-icon_v2')
            for item in amenities:
                if 'icon-bedrooms' in str(item):
                    bedrooms = str(item).split('>')[3].split('<')[0].strip()
                if 'icon-bathrooms' in str(item):
                    bath = str(item).split('>')[3].split('<')[0].strip()
                if 'icon-livingsize' in str(item):
                    floor_area = str(item).split('>')[3].split('<')[0].strip()
                if 'icon-land_size' in str(item):
                    land_area = str(item).split('>')[3].split('<')[0].strip()
        except AttributeError:
            bedrooms =np.nan # used numpy NaN objects instead of the string "an" to avoid errors when casting to integers later
            bath = np.nan
            floor_area = np.nan
        #print('bd:',bedrooms, '\n','ba:',bath, '\n','fa:',floor_area) # used for testing/debugging
        
        # get the geolocation
        geo_start = str(info).index('data-geo-point=')
        geo_end = str(info).index(']',geo_start) # Calculating the end is better than assuming it will be in a certain position as the number of positions after the comma varies in the original data
        geo_location = str(info)[geo_start+17:geo_end]
        geo_location = geo_location.replace(']','')
        geo_location = geo_location.replace('"','')
        geo_location = geo_location.replace(' ','')
        geo_location = geo_location.replace('d','')
        geo_location = geo_location.replace('a','')
        geo = geo_location.split(",")
        longitude = geo[0].replace(r'[^0-9.]', '')
        latitude = geo[1].replace(r'[^0-9.]', '')
        
        # search for the type of property. this is critical for analysis, as we do not want to compare plots with apartments or houses.
        cat_start = str(info).index('data-subcategories=')
        cat_end = str(info).index(']',cat_start)
        cat = str(info)[cat_start+21:cat_end] 
        cat = cat.replace('"','')
        subcat = cat.split(',')[1]
        cat = cat.split(',')[0]
        #print(cat, '\n',subcat) # used for testing/debugging
        
        link = info.a['href']
        # need to create an ID for the dict below. This will be our unique identifier in the df later
        # also, working with a dict seems more economic than appending a df
        id_var = str(page) + str(i)
        print(id_var)
        real_estate_dict[id_var] = {
                'description' : strip_accents(header),
                'location' : strip_accents(location),
                'price_PHP' : price.lstrip("₱ ").replace(',','').replace(' ',''),
                'bedrooms' : bedrooms,
                'bath' : bath,
                'floor_area_sqm' : floor_area.rstrip(" m²"),
                'land_area_sqm' : land_area.rstrip(" m²"),
                'category' : cat,
                'subcategory' : subcat,
                'latitude' : latitude,
                'longitude' : longitude,
                'link' : link}
        #print('\n++++++++ finished add ++++++++ \n')
                
    print(f'finished page {page}')

real_estate_df = pd.DataFrame.from_dict(real_estate_dict, orient='index')
real_estate_df["latitude"] = pd.to_numeric(real_estate_df["latitude"], downcast="float") 
real_estate_df["longitude"] = pd.to_numeric(real_estate_df["longitude"], downcast="float") 
real_estate_df["floor_area_sqm"] = pd.to_numeric(real_estate_df["floor_area_sqm"], downcast="float") 
real_estate_df["bedrooms"] = pd.to_numeric(real_estate_df["bedrooms"], downcast="integer") 
real_estate_df["bath"] = pd.to_numeric(real_estate_df["bath"], downcast="integer", errors='coerce') 
real_estate_df["price_PHP"] = pd.to_numeric(real_estate_df["price_PHP"], downcast="float") 
real_estate_df['date_accessed'] = pd.to_datetime('today').strftime('%Y-%m-%d')
real_estate_df['source'] = 'Lamudi'
real_estate_df['price_USD'] = round(real_estate_df['price_PHP']*0.021, 3)
# move the column 'price_USD' to the third position
cols = real_estate_df.columns.tolist()
cols = cols[:2] + [cols[-1]] + cols[2:-1]
real_estate_df = real_estate_df[cols]
# remove the outliers from the data. Please watch out for this value, it is currently eye-balled.
outlier_value = 1000000
real_estate_df = real_estate_df.loc[real_estate_df['price_USD'] < outlier_value]
real_estate_gdf_temp = gpd.GeoDataFrame(real_estate_df, geometry=gpd.points_from_xy(real_estate_df.longitude, real_estate_df.latitude), crs='EPSG:4326')

# let's adopt a UTM projection instead of the global one to increase geolocation precision
real_estate_gdf_temp = real_estate_gdf_temp.to_crs('EPSG:3265') 
# include the following line if you have an AOI polygon. I did.
# real_estate_gdf = real_estate_gdf_temp.clip(AOI_gdf, keep_geom_type=True) 
fig, ax = plt.subplots(figsize=(10, 10))

real_estate_gdf.plot('price_USD',cmap='viridis', legend=True, ax=ax, markersize=30,zorder=3)

# export the data
file_name = 'MAN_ECO_real_estate_prices_2024_P.shp'
real_estate_gdf.to_file(interim_path/file_name, encoding = 'utf-8')
