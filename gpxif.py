import sys
import os
import piexif
import gpxpy.parser as parser
from datetime import datetime
from dateutil import tz

def is_photo(filename):
    return filename.lower().split('.')[-1] in ('jpg', 'jpeg', 'tiff')

def gpxif(input_directory, gpx_file_path):
    #todo: I/O error checking

    import pytz

    location_history = build_location_history(gpx_file_path)

    for filename in os.listdir(input_directory):
        print 7 * '# ' + 'Input directory %s contains file %s (%s)' % (input_directory, filename, 'photo' if is_photo(filename) else 'not sure') + 7 * ' #'
        if is_photo(filename):
            photo_path = os.path.join(input_directory, filename)
            data_dict = piexif.load(photo_path)
            zero_dict = data_dict['0th']
            gps_dict = data_dict['GPS']
            exif_dict = data_dict['Exif']

            # get date taken
            time_taken = datetime.strptime(exif_dict[piexif.ExifIFD.DateTimeOriginal], '%Y:%m:%d %H:%M:%S')
            local_time_zone = pytz.timezone('Europe/Amsterdam')
            time_taken = local_time_zone.localize(time_taken)
            pt = location_history.get_by_time(time_taken)
            # print gps_dict
            # print '0th dict[GPSTag]: {0}'.format(zero_dict[piexif.ImageIFD.GPSTag])

            if is_useful_gps_data(gps_dict):
                print_gps_dict(gps_dict)
            else:
                print 'No GPS data! Photo {4} taken at {0} around point {1}, {2}, elevation {3}]'.format(time_taken, pt[0], pt[1],
                                                                                            pt[2], filename)
                # reset GPS dict to avoid conflicts
                gps_dict = dict()
                # zero_dict[piexif.ImageIFD.GPSTag] = 716
                # save it there, maybe it will help
                # data_dict['0th'] = zero_dict

                if pt[2] is not None:
                    gps_dict[piexif.GPSIFD.GPSAltitude] = (int(pt[2] * 100), 100)
                    gps_dict[piexif.GPSIFD.GPSAltitudeRef] = 0
                # todo: how to convert N/S, E/W ?
                gps_dict[piexif.GPSIFD.GPSLatitude] = frac_to_deg(abs(pt[0]))
                gps_dict[piexif.GPSIFD.GPSLatitudeRef] = 'N' if pt[0] > 0 else 'S'
                gps_dict[piexif.GPSIFD.GPSLongitude] = frac_to_deg(abs(pt[1]))
                gps_dict[piexif.GPSIFD.GPSLatitudeRef] = 'E' if pt[1] > 0 else 'W'

                utc_time = time_taken.astimezone(pytz.utc)

                gps_dict[piexif.GPSIFD.GPSDateStamp] = '{0}:{1}:{2}'.format(utc_time.year, utc_time.month, utc_time.day)
                gps_dict[piexif.GPSIFD.GPSTimeStamp] = ((utc_time.hour, 1), (utc_time.minute, 1), (utc_time.second, 1))

                data_dict['GPS'] = gps_dict
                exif_bytes = piexif.dump(data_dict)
                piexif.insert(exif_bytes, os.path.join(input_directory, filename))


    #exif_bytes = piexif.dump(exif_dict)
    #piexif.insert(exif_bytes, "foo.jpg")

def is_useful_gps_data(gps_dict):
    return piexif.GPSIFD.GPSAltitude in gps_dict and piexif.GPSIFD.GPSLatitude in gps_dict


def frac_to_deg(x):
    deg, d = divmod(x, 1)
    min, d = divmod(d*60, 1)
    sec = round(d * 60 * 100)
    return ((int(deg), 1), (int(min), 1), (int(sec), 100))


def print_gps_dict(gps_dict):

    keys = [piexif.GPSIFD.GPSLatitude, piexif.GPSIFD.GPSLatitudeRef, piexif.GPSIFD.GPSLongitude, piexif.GPSIFD.GPSLongitudeRef, piexif.GPSIFD.GPSAltitude, piexif.GPSIFD.GPSAltitudeRef, piexif.GPSIFD.GPSDateStamp, piexif.GPSIFD.GPSTimeStamp]

    values = [gps_dict[k] if k in gps_dict else None for k in keys]

    print 'GPS data in place: Lat: {0}[{1}], Lon: {2}[{3}], Alt: {4}[{5}], Date: {6}, Time: {7}'.format(*values)

def points_average(a, b, timestamp):
    assert a.time <= timestamp <= b.time
    time_span = abs((b.time - a.time).seconds)
    weight_a = time_span - abs((timestamp - a.time).seconds)
    weight_b = time_span - weight_a
    assert weight_b >= 0 and weight_a >= 0 and weight_b + weight_a == time_span
    print "timespan: {0}, WA: {1}, WB: {2}".format(time_span, weight_a, weight_b)

    avg_lat = (a.latitude * weight_a + b.latitude * weight_b)/time_span
    avg_lon = (a.longitude * weight_a + b.longitude * weight_b)/time_span
    avg_elev = None
    if a.elevation is None:
        avg_elev = b.elevation
    elif b.elevation is None:
        avg_elev = a.elevation
    else:
        avg_eleg = (a.elevation * weight_a + b.elevation * weight_b)/time_span

    return (avg_lat, avg_lon, avg_elev)


def build_location_history(inpath, target_tz=None):

    from_zone = tz.tzutc()
    to_zone = tz.tzlocal() if target_tz is None else tz.gettz(target_tz)

    gpx_parser = None
    with open(inpath, 'r') as gpx_file:
        gpx_parser = parser.GPXParser(gpx_file)
        gpx_parser.parse()

    gpx = gpx_parser.gpx

    all_points = []

    for track in gpx.tracks:
        for segment in track.segments:
            print 'Adding points from a segment'
            all_points += segment.points
            # for point in segment.points:
            #     print 'Point at ({0},{1}) -> {2}, at {3}'.format( point.latitude, point.longitude, point.elevation, point.time )

    for point in all_points:
        utc_time = point.time.replace(tzinfo=from_zone)
        point.time = utc_time.astimezone(to_zone)

    # for waypoint in gpx.waypoints:
    #     print 'waypoint {0} -> ({1},{2})'.format( waypoint.name, waypoint.latitude, waypoint.longitude )
    #
    # for route in gpx.routes:
    #     print 'Route:'
    #     for point in route:
    #         print 'Point at ({0},{1}) -> {2}'.format( point.latitude, point.longitude, point.elevation )

    return LocationHistory(all_points)


def print_exif_dict(exif_dict):
    for tag in dir(piexif.GPSIFD):
        tag_name = eval('piexif.GPSIFD.%s' % tag)
        if tag_name in exif_dict:
            print 'tag %s = %s' % (tag, exif_dict[eval('piexif.GPSIFD.%s' % tag)])

class LocationHistory(object):

    MODE_CLOSEST = 1
    MODE_INTERPOLATE = 2

    def __init__(self, points):
        self.points = points

    def get_by_time(self, time):
        if self.points[0].time >= time:
            return (self.points[0].latitude, self.points[0].longitude, self.points[0].elevation)
        elif self.points[-1].time <= time:
            return (self.points[-1].latitude, self.points[0].longitude, self.points[0].elevation)
        else:
            for i in range(1, len(self.points)):
                if self.points[i].time > time and self.points[i-1].time <= time:
                    a = self.points[i-1]
                    b = self.points[i]
                    rslt = points_average(a, b, time)
                    print 'Averaging {0} x {1} @ {2} ({3}) and {4} x {5} @ {6} ({7}) for {8} gave {9}'.format(
                        a.latitude, a.longitude, a.elevation, a.time, b.latitude, b.longitude, b.elevation, b.time, time, rslt
                    )
                    return rslt



if __name__ == '__main__':
    gpxif(sys.argv[1], sys.argv[2])