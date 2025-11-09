import numpy as np
import xarray as xr
import pandas as pd

LAT = 37.46
LON = 126.9483
SOLAR_CONSTANT = 1365
DAY_OF_SUMMER_SOLSTICE = 173
DAYS_IN_YEAR = 365
TRANSMISSIVITY = 0.75
EMISSIVITY_S = 0.95
SB_CONSTANT = 5.67 * 1.0e-8
ALBEDO = 0.3
C_SOIL_DRY = 2.0 * 1.0e6 # K/m3/K
Z_12 = 0.07 # m
Z_23 = 0.35 # m
C_SOIL = C_SOIL_DRY * Z_12 # J/m2/K
C_SOIL_1_2 = C_SOIL_DRY * Z_12 # J/m2/K
C_SOIL_2_3 = C_SOIL_DRY * Z_23 # J/m2/K
KARMAN = 0.4 # von Karman constant
G   = 9.81               # Gravitational acceleration [m/s2]
P_1000mb = 100000.0      # Pressure at 1000 mb [Pa]
P_SFC    = 101300.0      # Surface pressure [Pa]
R_D = 287.0              # Gas constant of dry air [J/K/kg]
C_P = 7.0 * R_D / 2.0    # the specific heat at constant pressure [J/K/kg]
R_OVER_C_P = R_D / C_P
THETA_SAT = 0.45  #m3/m3
THETA_FC  = 0.35  #m3/m3
THETA_PWP = 0.15  #m3/m3
LV = 2.501e6 # J/kg

def calculate_solar_radiation_toa(lat_degree, lon_degree, datetime_UTC):

    # Get day of year
    day_of_year = datetime_UTC.dayofyear

    # Latitude/longitude in radians
    latitude  = lat_degree * np.pi / 180
    longitude = lon_degree * np.pi / 180

    # Solar declination angle in radians
    solar_declination_angle = 23.45 * np.pi / 180 * np.cos(2 * np.pi * (day_of_year - DAY_OF_SUMMER_SOLSTICE) / DAYS_IN_YEAR)

    # Local hour angle in radians
    local_hour = ( datetime_UTC.hour - 12 ) * np.pi / 12 + longitude

    # Calculate the cosine of the zenith angle
    cos_zenith = np.sin(latitude) * np.sin(solar_declination_angle) + \
                 np.cos(latitude) * np.cos(solar_declination_angle) * np.cos(local_hour)
    cos_zenith = np.clip(cos_zenith, 0, 1)  # avoid negative irradiance

    # Earth-Sun distance correction factor, d (dimensionless)
    # Fractional year in radians
    gamma = 2 * np.pi * (day_of_year - 1) / DAYS_IN_YEAR

    d = 1.00011 + 0.034221 * np.cos(gamma) + 0.00128 * np.sin(gamma) \
        + 0.000719 * np.cos(2 * gamma) + 0.000077 * np.sin(2 * gamma)

    # solar radiation at the top of the atmosphere at the given latitude, longitude and time (W/m²)
    solar_radiation_toa = SOLAR_CONSTANT * cos_zenith * d**2

    return solar_radiation_toa



def calculate_SWd(lat_degree, lon_degree, datetime_UTC):

    solar_radiation_toa = calculate_solar_radiation_toa(lat_degree, lon_degree, datetime_UTC)
    SWd = solar_radiation_toa * TRANSMISSIVITY

    # SWd = xr.Dataset(
    #              {'SWd': (['time'], np.array(SWd))},
    #              coords={'time': datetime_UTC},
    #              attrs={'units': 'W/m2',
    #                     'long_name': 'Downward shortwave radiation'},
    # )
    SWd = xr.DataArray(
                 np.array(SWd),
                 coords={'time': datetime_UTC},
                 dims=['time'],
                 attrs={'units': 'W/m2',
                        'long_name': 'Downward shortwave radiation'},
    )

    return SWd


def calculate_LWu(Ts):
    LWu = EMISSIVITY_S * SB_CONSTANT * Ts**4

    return LWu



def read_input_bondville(file_path='../data/bondville.dat'):

    column_names = ['year', 'month', 'day', 'hour', 'minute', 'windspeed', 'temperature', 'humidity', 'pressure', 'shortwave', 'longwave', 'precipitation']

    df = pd.read_csv(f'{file_path}',
                        skiprows=54,
                        sep='\s+',  # separate by whitespace
                        names=column_names)

    # Add time column by combining date/time columns
    df['time'] = pd.to_datetime(df[['year', 'month', 'day', 'hour', 'minute']])

    # Reorder columns to put time first & remove 'year', 'month', 'day', 'hour', 'minute' columns
    cols = ['time'] + [col for col in df.columns if col != 'time']
    df = df[cols]
    df = df[['time', 'windspeed', 'temperature', 'humidity', 'pressure', 'shortwave', 'longwave', 'precipitation']]

    # Set index to time column
    df = df.set_index('time')

    # Add 273.15 to temperature column to convert the unit from C to K
    df['temperature'] = df['temperature'] + 273.15

    # Mutiply 100 to presssure column to convert the unit from hPa to Pa
    df['pressure'] = df['pressure'] * 100

    # Convert precipitation column from inches/30min to mm/day
    df['precipitation'] = df['precipitation'] * 25.4 / 1800 * 86400.

    # Convert to xarray dataset
    xr_dataset = xr.Dataset.from_dataframe(df)

    # Add units
    units = {'windspeed': 'm/s',
             'temperature': 'K',
             'humidity': '%',
             'pressure': 'Pa',
             'shortwave': 'W/m2',
             'longwave': 'W/m2',
             'precipitation': 'mm/day'}
    for var, unit in units.items():
        xr_dataset[var].attrs['units'] = unit

    return xr_dataset



def calculate_bulk_richardson_number(Ts, Ta, Pa, wind_speed, zr):
    '''
    Adapted lines from revise MM5 surface-layer scheme.
    Input:
        Ta: air temperature [K]
        Pa: air pressure [Pa]
        wind_speed: wind speed [m/s]
        zr: the height of the model lowest layer [m]
    '''

    theta_a_conversion = ( P_1000mb / Pa) ** R_OVER_C_P
    theta_a = Ta * theta_a_conversion

    # Assume surface pressure is 1013 hPa
    theta_s_conversion = ( P_1000mb / P_SFC) ** R_OVER_C_P
    theta_s = Ts * theta_s_conversion
    
    dtheta = theta_a - theta_s 

    g_over_theta_a = G / theta_a
    
    Rib = g_over_theta_a * zr * dtheta / (wind_speed**2)

    return Rib



def calculate_psim_unstable(zolf):
    X=(1.-16.*zolf)**.25
    psimk=2*np.log(0.5*(1+X))+np.log(0.5*(1+X*X))-2.*np.arctan(X)+2.*np.arctan(1.)
    
    ym=(1.-10.*zolf)**0.33
    psimc=(3./2.)*np.log((ym**2.+ym+1.)/3.)-np.sqrt(3.)*np.arctan((2.*ym+1)/np.sqrt(3.))+4.*np.arctan(1.)/np.sqrt(3.)

    psim_unstable_full=(psimk+zolf**2*(psimc))/(1+zolf**2.)
    return psim_unstable_full


def calculate_psim_stable(zolf):
    psim_stable_full=-6.1*np.log(zolf+(1+zolf**2.5)**(1./2.5))
    return psim_stable_full


def calculate_psih_unstable(zolf):
    y=(1.-16.*zolf)**.5
    psihk=2.*np.log((1+y)/2.)
    
    yh=(1.-34.*zolf)**0.33
    psihc=(3./2.)*np.log((yh**2.+yh+1.)/3.)-np.sqrt(3.)*np.arctan((2.*yh+1)/np.sqrt(3.))+4.*np.arctan(1.)/np.sqrt(3.)

    psih_unstable_full=(psihk+zolf**2*(psihc))/(1+zolf**2.)
    return psih_unstable_full


def calculate_psih_stable(zolf):
    psih_stable_full=-5.3*np.log(zolf+(1+zolf**1.1)**(1./1.1))
    return psih_stable_full


def calculate_z_over_L(Rib, zr, z0):
    
    if Rib < 0:
        x1, x2 = -5.0, 0.0
    else:
        x1, x2 = 0.0, 5.0

    fx1 = zolri2(x1,Rib,zr,z0)
    fx2 = zolri2(x2,Rib,zr,z0)
    iter = 0
    zolir = 0.0

    while np.abs(x2 - x1) > 0.01:
        if iter == 10:
            break

        if fx1 == fx2:
            break

        if np.abs(fx2) < np.abs(fx1):
            x1=x1-fx1/(fx2-fx1)*(x2-x1)
            fx1=zolri2(x1,Rib,zr,z0)
            zolri=x1
        else:
            x2=x2-fx2/(fx2-fx1)*(x2-x1)
            fx2=zolri2(x2,Rib,zr,z0)
            zolri=x2
        
        iter += 1
    
    return zolri


def zolri2(zol2, br2, zr, z0):
    if zol2*br2 < 0.0:
        zol2 = 0.0

    zol20=zol2*z0/zr # z0/L
    # zol3=zol2+zol20 # (z+z0)/L
    zol3 = zol2 # In this code, z0/L is not considered for the simplicity.

    if br2 < 0:
        psix2=np.log((zr)/z0)-(calculate_psim_unstable(zol3) - calculate_psim_unstable(zol20))
        psih2=np.log((zr)/z0)-(calculate_psih_unstable(zol3) - calculate_psih_unstable(zol20))
    else:
        psix2=np.log((zr)/z0)-(calculate_psim_stable(zol3) - calculate_psim_stable(zol20))
        psih2=np.log((zr)/z0)-(calculate_psih_stable(zol3) - calculate_psih_stable(zol20))

    zolri2=zol2*psih2/psix2**2-br2

    return zolri2



def calculate_q_sat(Ta, Pa):
    
    e_sat = 0.611 * np.exp(17.27 * (Ta - 273.15) / (Ta - 273.15 + 237.3)) * 1000  # Pa
    q_sat = 0.622 * e_sat / (Pa - e_sat)  # kg/kg

    return q_sat



def read_ASOS_at_Daegu(file_path='../data/ASOS_processed_2012033100-2012041000.nc', time_interval='original', time_end='2012-04-05 00:00'):

    ASOS = xr.open_dataset(file_path)
    ASOS_Daegu = ASOS.sel(STN=143) # Daegu station
    ASOS_Daegu = ASOS_Daegu.sel(time=slice('2012-04-01 00:00', time_end))

    # Assign observed variables
    Ta         = ASOS_Daegu['TA'] + 273.15        # Convert C to K
    Ts         = ASOS_Daegu['TS'] + 273.15        # Convert C to K
    Pa         = ASOS_Daegu['PA'] * 100.          # Convert hPa to Pa
    RH         = ASOS_Daegu['HM']                 # %
    Qa         = RH / 100.0 * calculate_q_sat(Ta, Pa)  # kg/kg
    wind_speed = ASOS_Daegu['WS']                 # m/s
    SWd = ASOS_Daegu['SI'] * 1.0e6 / 3600  # Convert MJ/m2 to W/m2
    SWd = xr.where(SWd < 0, 0, SWd)        # Set negative SWd to 0
    R          = ASOS_Daegu['RN']                 # mm/hour
    R          = xr.where(R < 0, 0, R)

    if time_interval != 'original':
        # Interpolate hourly data to minutely data to avoid numerical instability
        minutely_time = pd.date_range(
            start=Ta.time[0].item(), 
            end=Ta.time[-1].item(), 
            freq=time_interval
        )

        Ta = Ta.interp(time=minutely_time)
        Ts = Ts.interp(time=minutely_time)
        Pa = Pa.interp(time=minutely_time)
        Qa = Qa.interp(time=minutely_time)
        wind_speed = wind_speed.interp(time=minutely_time)
        SWd = SWd.interp(time=minutely_time)
        R = R.interp(time=minutely_time)

    rho        = Pa / (R_D * Ta) # kg/m3

    Ts = (Ts) * 0.2 + Ta * 0.8 # Blend air and surface temperature as surface temperature is too spiky

    return Ta, Ts, Pa, Qa, wind_speed, SWd, rho, R, ASOS_Daegu


def calculate_moisture_availability(theta, Qa, q_sat):

    beta = 0.25 * (1 - np.cos(theta / THETA_FC * np.pi)) ** 2
    beta_limit = Qa / q_sat
    beta_limit = np.where(beta_limit > 1.0, 1.0, beta_limit)

    beta = np.where(beta > beta_limit, beta, beta_limit)
    beta = np.where(theta > THETA_FC, 1.0, beta)

    return beta