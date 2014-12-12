# -*- coding: utf-8 -*-
from __future__ import unicode_literals

'''
Add the cleangeometry function in a data migration. 

There are several versions of this function. 
 - The one provided below
 - In newer (>2) versions of postgis, it's included and called st_cleangeometry
 - In other versions, there is a semi-compatible function called st_makevalid

For the moment, we'll use the custom version below. 
'''



from django.db import models, migrations

CLEANGEOMETRY_SQL = '''
-- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
-- 
-- $Id: cleanGeometry.sql 2008-04-24 10:30Z Dr. Horst Duester $
--
-- cleanGeometry - remove self- and ring-selfintersections from 
--                 input Polygon geometries 
-- http://www.sogis.ch
-- Copyright 2008 SO!GIS Koordination, Kanton Solothurn, Switzerland
-- Version 1.0
-- contact: horst dot duester at bd dot so dot ch
--
-- This is free software; you can redistribute and/or modify it under
-- the terms of the GNU General Public Licence. See the COPYING file.
-- This software is without any warrenty and you use it at your own risk
--  
-- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -


CREATE OR REPLACE FUNCTION cleanGeometry(geometry) RETURNS geometry AS $$
DECLARE
  inGeom ALIAS for $1;
  outGeom geometry;
  tmpLinestring geometry;

BEGIN
  
  outGeom := NULL;
  
-- Clean Process for Polygon 
  IF (GeometryType(inGeom) = 'POLYGON' OR GeometryType(inGeom) = 'MULTIPOLYGON') THEN

-- Only process if geometry is not valid, 
-- otherwise put out without change
    if not isValid(inGeom) THEN
    
-- create nodes at all self-intersecting lines by union the polygon boundaries
-- with the startingpoint of the boundary.  
      tmpLinestring := st_union(st_multi(st_boundary(inGeom)),st_pointn(boundary(inGeom),1));
      outGeom = buildarea(tmpLinestring);      
      IF (GeometryType(inGeom) = 'MULTIPOLYGON') THEN      
        RETURN st_multi(outGeom);
      ELSE
        RETURN outGeom;
      END IF;
    else    
      RETURN inGeom;
    END IF;


------------------------------------------------------------------------------
-- Clean Process for LINESTRINGS, self-intersecting parts of linestrings 
-- will be divided into multiparts of the mentioned linestring 
------------------------------------------------------------------------------
  ELSIF (GeometryType(inGeom) = 'LINESTRING') THEN
    
-- create nodes at all self-intersecting lines by union the linestrings
-- with the startingpoint of the linestring.  
    outGeom := st_union(st_multi(inGeom),st_pointn(inGeom,1));
    RETURN outGeom;
  ELSIF (GeometryType(inGeom) = 'MULTILINESTRING') THEN 
    outGeom := multi(st_union(st_multi(inGeom),st_pointn(inGeom,1)));
    RETURN outGeom;
  ELSE 
    RAISE NOTICE 'The input type % is not supported',GeometryType(inGeom);
    RETURN inGeom;
  END IF;	  
END;
$$ LANGUAGE 'plpgsql' VOLATILE;
'''
    
REVERSE_CLEANGEOMETRY_SQL = '''
DROP FUNCTION cleanGeometry;
'''


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.RunSQL(CLEANGEOMETRY_SQL, REVERSE_CLEANGEOMETRY_SQL)
    ]
