"""Testes do algoritmo de não sobreposição, com geometria compacta."""
import io
import unittest
from reportlab.pdfgen import canvas
from app.services.plant_label_layout import LabelLayout, Box


class LabelPlacementTests(unittest.TestCase):
    def test_boxes_overlap_and_viewport(self):
        a=Box(10,10,20,10)
        self.assertTrue(a.intersects(Box(28,14,10,10)))
        self.assertFalse(a.intersects(Box(60,60,10,10)))
        self.assertTrue(a.inside(Box(0,0,100,100)))

    def test_two_labels_never_occupy_the_same_box(self):
        pdf=canvas.Canvas(io.BytesIO())
        engine=LabelLayout((0,0,240,130))
        for n in range(3):
            self.assertTrue(engine.place(pdf,["Ponto longo V-001"],(80,65)))
        self.assertEqual(len(engine.reserved),3)
        for i,a in enumerate(engine.reserved):
            for b in engine.reserved[i+1:]:
                self.assertFalse(a.intersects(b), (a,b))

    def test_callout_when_compact_cluster_is_blocked(self):
        pdf=canvas.Canvas(io.BytesIO())
        engine=LabelLayout((0,0,220,150))
        engine.reserved.append(Box(45,35,130,80))
        self.assertTrue(engine.place(pdf,["Confrontante"],(105,70),
                        offsets=[(0,0)],minimum=6.0,desired=6.0))
        self.assertEqual(len(engine.callouts),1)

    def test_rejects_unreadable_impossible_placement(self):
        pdf=canvas.Canvas(io.BytesIO())
        engine=LabelLayout((0,0,55,30))
        with self.assertRaisesRegex(ValueError,"sobreposição"):
            engine.place(pdf,["NOME EXTENSO DE CONFRONTANTE"],(26,15))


if __name__ == "__main__":
    unittest.main()
