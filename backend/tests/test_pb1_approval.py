import unittest
from copy import deepcopy
from app.services.pb1_approval import validate_pb1_vertices, validate_pb1_perimeter

class PB1ApprovalTests(unittest.TestCase):
    def setUp(self):
        self.v = dict(name="TEST-V-1", sigef_vertex_code="TEST-V-1", sigef_method="PB1",
            latitude=.4, longitude=-51.4, boundary_type="LN1", height_reference_confirmed=True,
            ellipsoidal_height_m=-10., sigma_lon_m=.8, sigma_lat_m=.6, sigma_h_m=.2)
        self.draft=[dict(name=self.v["name"],latitude=.4,longitude=-51.4)]
        self.preview=dict(sigma_origin="DECLARED",points=[dict(vertex_id=self.v["name"],
            latitude=.4,longitude=-51.4,status="DECLARED_REFERENCE",h_ellipsoidal_m=-10.,
            sigma_e_m=.8,sigma_n_m=.6,sigma_h_m=.2)])
    def approve(self,category="NATURAL",reason=""):
        return validate_pb1_vertices([self.v],self.draft,self.preview,"TEST",category,reason)
    def test_documented_values(self):
        self.assertTrue(self.approve()[0]["derived_calculation"]["accuracy_verified"])
    def test_estimated_pec_rejected(self):
        self.preview["sigma_origin"]="PEC_REFERENCE_ISOTROPIC_ESTIMATE"
        with self.assertRaisesRegex(ValueError,"PEC"):
            self.approve()
    def test_changed_value(self):
        self.v["ellipsoidal_height_m"]=-11.
        with self.assertRaisesRegex(ValueError,"atributo diferente"):
            self.approve()
    def test_limit_category(self):
        self.v["boundary_type"]="LA1"
        with self.assertRaisesRegex(ValueError,"categoria"):
            self.approve()
    def test_inaccessible_reason(self):
        with self.assertRaisesRegex(ValueError,"inacessibilidade"):
            self.approve("INACCESSIBLE")
    def test_wrong_prefix(self):
        self.v["sigef_vertex_code"]="VIRTUAL-V-1"
        with self.assertRaisesRegex(ValueError,"credenciado"):
            self.approve()
    def test_coordinate_changed(self):
        self.v["latitude"]+=.001
        with self.assertRaisesRegex(ValueError,"coordenada"):
            self.approve()
    def test_perimeter_wrong_order(self):
        a=dict(name="A",sigef_method="PG1",latitude=.41,longitude=-51.4)
        b=dict(name="B",sigef_method="PG1",latitude=.39,longitude=-51.39)
        c=dict(name="C",sigef_method="PG1",latitude=.39,longitude=-51.41)
        top=dict(boundary=[a,b,c],pb1_draft=self.draft,pb1_closure={"start":"A"})
        with self.assertRaisesRegex(ValueError,"ordem"):
            validate_pb1_perimeter([a,b,self.v,c],top)
