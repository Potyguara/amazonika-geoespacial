import unittest
from math import hypot
from pyproj import Geod
from app.services.sgl_metrics import sgl_metrics, puissant_azimuth
from app.services.plant_memorial_v2 import prepare_parcels
from app.services.topcon_perimeter_review import review_topcon_perimeter
from app.api.routes.technical_pieces import parcel_metrics, ParcelMetricsInput

class SGLTests(unittest.TestCase):
    def setUp(self):
        # Quadrilátero de teste, construído por geodésia GRS80.
        geod=Geod(ellps="GRS80")
        a=(-51.4,.4)
        b=geod.fwd(*a,90,100)[:2]
        c=geod.fwd(*b,180,100)[:2]
        d=geod.fwd(*a,180,100)[:2]
        self.points=[a,b,c,d]
        self.h=[100.,100.,100.,100.]

    def test_local_square(self):
        m=sgl_metrics(self.points,self.h)
        self.assertAlmostEqual(m["area_ha"],1.,places=4)
        self.assertAlmostEqual(m["perimeter_m"],400.,places=1)
        self.assertEqual(m["area_method"],"SGL_GRS80")

    def test_height_influences_area(self):
        base=sgl_metrics(self.points,[0.]*4)
        high=sgl_metrics(self.points,[1000.]*4)
        self.assertGreater(high["area_ha"],base["area_ha"])
        self.assertAlmostEqual(high["area_ha"]/base["area_ha"],(1+1000/6378137)**2,places=5)

    def test_missing_height_rejected(self):
        with self.assertRaisesRegex(ValueError,"alturas elipsoidais"):
            sgl_metrics(self.points,[None,0.,0.,0.])

    def test_same_metrics_across_services(self):
        raw=dict(name="Teste",geometry={"type":"Polygon","coordinates":[self.points+[self.points[0]]]},
                 altitudes_m=self.h)
        parcel=prepare_parcels([raw])[0]
        result=parcel_metrics(ParcelMetricsInput(parcels=[raw]),None)["parcels"][0]
        vertices=[dict(name=str(i),longitude=lon,latitude=lat,ellipsoidal_height_m=h,height_reference_confirmed=True)
                  for i,((lon,lat),h) in enumerate(zip(self.points,self.h))]
        checked=review_topcon_perimeter(vertices)
        self.assertEqual(result["area_ha"],parcel.area_ha)
        self.assertEqual(result["perimeter_m"],parcel.perimeter)
        self.assertEqual(checked["area_ha"],round(parcel.area_ha,4))
        self.assertEqual(checked["perimeter_m"],round(parcel.perimeter,3))
        self.assertEqual(checked["metrics_method"],"SGL_GRS80")
        raw["altitudes_m"]=[None,100.,100.,100.]
        self.assertEqual(prepare_parcels([raw])[0].metrics_method,"GEODESIC_PRELIMINARY")

    def test_puissant_quadrants(self):
        geod=Geod(ellps="GRS80")
        for lon,lat in [(-51.4,.4),(-49.,-25.5),(-60.,-12.)]:
            for az in [0,45,90,135,180,225,270,315]:
                for distance in [10,1500,15000]:
                    end=geod.fwd(lon,lat,az,distance)[:2]
                    calculated=puissant_azimuth(lon,lat,*end)
                    error=abs((calculated-az+180)%360-180)*3600
                    self.assertLess(error,1.0,(lon,lat,az,distance,error))

    def test_puissant_ufpr_example_against_independent_geodesic(self):
        a=(-49-2/60-11.4622/3600,-25-33/60-6.918/3600)
        b=(-49-6/60-27.1595/3600,-25-31/60-11.190/3600)
        expected=Geod(ellps="GRS80").inv(*a,*b)[0]%360
        self.assertLess(abs(puissant_azimuth(*a,*b)-expected)*3600,1.0)

    def test_puissant_domain(self):
        with self.assertRaises(ValueError):
            puissant_azimuth(-51.,0.,-49.,0.)
        with self.assertRaises(ValueError):
            puissant_azimuth(-51.,0.,-51.,0.)
