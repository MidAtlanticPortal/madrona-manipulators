from django.contrib.gis.geos import Polygon
from django.db import connection
from django.contrib.gis.geos import fromstr
from math import pi
from django.conf import settings

def LargestPolyFromMulti(geom): 
    """ takes a polygon or a multipolygon geometry and returns only the largest polygon geometry"""
    if geom.num_geom > 1:
        largest_area = 0.0
        for g in geom: # find the largest polygon in the multi polygon 
            if g.area > largest_area:
                largest_geom = g
                largest_area = g.area
    else:
        largest_geom = geom
    return largest_geom


def LargestLineFromMulti(geom):
    """ takes a line or a multiline geometry and returns only the longest line geometry"""
    if geom.num_geom > 1:
        largest_length = 0.0
        for g in geom: # find the largest polygon in the multi polygon
            if g.length > largest_length:
                largest_geom = g
                largest_length = g.length
    else:
        largest_geom = geom
    return largest_geom  


def angle(pnt1,pnt2,pnt3):
    """
    Return the angle in radians between line(pnt2,pnt1) and line(pnt2,pnt3)
    """
    cursor = connection.cursor()
    if pnt1.srid:
        query = "SELECT abs(ST_Azimuth(ST_PointFromText(\'%s\',%i), ST_PointFromText(\'%s\',%i) ) - ST_Azimuth(ST_PointFromText(\'%s\',%i), ST_PointFromText(\'%s\',%i)) )" % (pnt2.wkt,pnt2.srid,pnt1.wkt,pnt1.srid,pnt2.wkt,pnt2.srid,pnt3.wkt,pnt3.srid)
    else:
        query = "SELECT abs(ST_Azimuth(ST_PointFromText(\'%s\'), ST_PointFromText(\'%s\') ) - ST_Azimuth(ST_PointFromText(\'%s\'), ST_PointFromText(\'%s\')) )" % (pnt2.wkt,pnt1.wkt,pnt2.wkt,pnt3.wkt)
    #print query
    cursor.execute(query)
    row = cursor.fetchone()
    return row[0]

def angle_degrees(pnt1,pnt2,pnt3):
    """
    Return the angle in degrees between line(pnt2,pnt1) and line(pnt2,pnt3)
    """
    rads = angle(pnt1,pnt2,pnt3)
    return rads * (180 / pi)

def spike_ring_indecies(line_ring,threshold=0.01):
    """
    Returns a list of point indexes if ring contains spikes (angles of less than threshold degrees).
    Otherwise, an empty list.
    """
    radian_thresh = threshold * (pi / 180)
    spike_indecies = []
    for i,pnt in enumerate(line_ring.coords):
        if(i == 0 and line_ring.num_points > 3): # The first point  ...which also equals the last point
            p1_coords = line_ring.coords[len(line_ring.coords) - 2]
        elif(i == line_ring.num_points - 1): # The first and last point are the same in a line ring so we're done
            break
        else:
            p1_coords = line_ring.coords[i - 1]

        # set up the points for the angle test.
        p1_str = 'POINT (%f %f), %i' % (p1_coords[0], p1_coords[1], settings.GEOMETRY_DB_SRID)
        p1 = fromstr(p1_str)
        p2_str = 'POINT (%f %f), %i' % (pnt[0],pnt[1],settings.GEOMETRY_DB_SRID)
        p2 = fromstr(p2_str)
        p3_coords = line_ring.coords[i + 1]
        p3_str = 'POINT (%f %f), %i' % (p3_coords[0], p3_coords[1], settings.GEOMETRY_DB_SRID)
        p3 = fromstr(p3_str)
        if(angle(p1,p2,p3) <= radian_thresh):
            spike_indecies.append(i)

    return spike_indecies

def remove_spikes(poly,threshold=0.01):
    """
    Looks for spikes (angles < threshold degrees) in the polygons exterior ring.  If there are spikes,
    they will be removed and a polygon (without spikes) will be returned.  If no spikes are found, method
    will return original geometry.

    NOTE: This method does not examine or fix interior rings.  So far those haven't seemed to have been a problem.
    """
    line_ring = poly.exterior_ring
    spike_indecies = spike_ring_indecies(line_ring,threshold=threshold)
    if(spike_indecies):
        for i,org_index in enumerate(spike_indecies):
            if(org_index == 0): # special case, must remove first and last point, and add end point that overlaps new first point
                # get the list of points
                pnts = list(line_ring.coords)
                # remove the first point
                pnts.remove(pnts[0])
                # remove the last point
                pnts.remove(pnts[-1])
                # append a copy of the new first point (old second point) onto the end so it makes a closed ring
                pnts.append(pnts[0])
                # replace the old line ring
                line_ring = LinearRing(pnts)
            else:
                line_ring.remove(line_ring.coords[org_index])
        poly.exterior_ring = line_ring
    return poly
def clean_geometry(geom):
    # TODO:
    # There are updated versions of the cleangeometry.sql code. Update it. 
    # Also, there's no particular reason why cleangeometry() can't be written
    # as a python function (which would remove the dependency on installing a 
    # custom function in the database). 
    # All of the used postgis functions use GEOS as far as I can tell, and we
    # have a full GEOS api. 
    # The ones that aren't directly GEOS could also be ported, i.e., 
    # https://github.com/postgis/postgis/blob/12ea21877345f20bc691716c6edd9c006471ce76/liblwgeom/lwgeom_geos.c  
    """Send a geometry to the cleanGeometry stored procedure and get the cleaned geom back."""
    cursor = connection.cursor()
    query = "select cleangeometry(st_geomfromewkt(\'%s\')) as geometry" % geom.ewkt
    cursor.execute(query)
    row = cursor.fetchone()
    newgeom = fromstr(row[0])

    if geom.geom_type == "Polygon":
        # sometimes, clean returns a multipolygon
        geometry = LargestPolyFromMulti(newgeom)
    else:
        geometry = newgeom

    if not geometry.valid or (geometry.geom_type != 'Point' and geometry.num_coords < 2):
        raise Exception("I can't clean this geometry. Dirty, filthy geometry. This geometry should be ashamed.")
    else:
        return geometry


# transforms the geometry to the given srid, checks it's validity and 
# cleans it if necessary, transforms it back into the original srid and
# cleans again if needed before returning 
# Note, it does not scrub the geometry before transforming, so if needed
# call check_validity(geo, geo.srid) first.
def ensure_clean(geo, srid):
    old_srid = geo.srid
    if geo.srid is not srid:
        geo.transform(srid)
    geo = clean_geometry(geo)
    if not geo.valid:
        raise Exception("ensure_clean could not produce a valid geometry.")
    if geo.srid is not old_srid:
        geo.transform(old_srid)
        geo = clean_geometry(geo)
        if not geo.valid:
            raise Exception("ensure_clean could not produce a valid geometry.")
    return geo

def ComputeLookAt(geometry):

    lookAtParams = {}

    DEGREES = pi / 180.0
    EARTH_RADIUS = 6378137.0

    trans_geom = geometry.clone()
    trans_geom.transform(settings.GEOMETRY_DB_SRID) # assuming this is an equal area projection measure in meters

    w = trans_geom.extent[0]
    s = trans_geom.extent[1]
    e = trans_geom.extent[2]
    n = trans_geom.extent[3]

    center_lon = trans_geom.centroid.y
    center_lat = trans_geom.centroid.x

    lngSpan = (Point(w, center_lat)).distance(Point(e, center_lat)) 
    latSpan = (Point(center_lon, n)).distance(Point(center_lon, s))

    aspectRatio = 1.0

    PAD_FACTOR = 1.5 # add 50% to the computed range for padding

    aspectUse = max(aspectRatio, min((lngSpan / latSpan),1.0))
    alpha = (45.0 / (aspectUse + 0.4) - 2.0) * DEGREES # computed experimentally;

    # create LookAt using distance formula
    if lngSpan > latSpan:
        # polygon is wide
        beta = min(DEGREES * 90.0, alpha + lngSpan / 2.0 / EARTH_RADIUS)
    else:
        # polygon is taller
        beta = min(DEGREES * 90.0, alpha + latSpan / 2.0 / EARTH_RADIUS)

    lookAtParams['range'] = PAD_FACTOR * EARTH_RADIUS * (sin(beta) *
        sqrt(1.0 / pow(tan(alpha),2.0) + 1.0) - 1.0)

    trans_geom.transform(4326)

    lookAtParams['latitude'] = trans_geom.centroid.y
    lookAtParams['longitude'] = trans_geom.centroid.x
    lookAtParams['tilt'] = 0
    lookAtParams['heading'] = 0

    return lookAtParams
    
def isCCW(ring):
    """
    Determines if a LinearRing is oriented counter-clockwise or not
    """
    area = 0.0
    for i in range(0,len(ring) - 1):
        p1 = ring[i]
        p2 = ring[i + 1]
        area += (p1[1] * p2[0]) - (p1[0] * p2[1])

    if area > 0:
        return False
    else:
        return True

def forceRHR(polygon):
    """
    reverses rings so that polygon follows the Right-hand rule
    exterior ring = clockwise
    interior rings = counter-clockwise
    """
    assert polygon.geom_type == 'Polygon'
    if polygon.empty:
        return poly
    exterior = True
    rings = []
    for ring in polygon:
        assert ring.ring # Must be a linear ring at this point
        if exterior:
            if isCCW(ring):
                ring.reverse()
            exterior = False
        else:
            if not isCCW(ring):
                ring.reverse()
        rings.append(ring)
    poly = Polygon(*rings)
    return poly

def forceLHR(polygon):
    """
    reverses rings so that geometry complies with the LEFT-hand rule
    Google Earth KML requires this oddity
    exterior ring = counter-clockwise
    interior rings = clockwise
    """
    assert polygon.geom_type == 'Polygon'
    assert not polygon.empty
    exterior = True
    rings = []
    for ring in polygon:
        assert ring.ring # Must be a linear ring at this point
        if exterior:
            if not isCCW(ring):
                ring.reverse()
            exterior = False
        else:
            if isCCW(ring):
                ring.reverse()
        rings.append(ring)
    poly = Polygon(*rings)
    return poly
