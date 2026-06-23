import os
import tempfile
import unittest

import dayone_to_enex as conv


class HtmlConversionTests(unittest.TestCase):
    def test_html_note_embeds_local_images_and_skips_export_chrome(self):
        with tempfile.TemporaryDirectory() as tmp:
            img_dir = os.path.join(tmp, "Images")
            os.mkdir(img_dir)
            img_path = os.path.join(img_dir, "recipe.jpg")
            with open(img_path, "wb") as f:
                f.write(b"fake image bytes")

            html_path = os.path.join(tmp, "Recipe.html")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write("""<!doctype html>
<html>
  <head>
    <title>Head title</title>
    <style>body { font-family: Helvetica; }</style>
    <script>window.bad = true;</script>
  </head>
  <body>
    <div class="recipe">
      <img src="Images/recipe.jpg" alt="Recipe image"/>
      <h1>Recipe &amp; Dinner</h1>
      <p><strong>Prep:</strong> 15 min <a href="https://example.com">source</a></p>
    </div>
    <div class="pswp"><button>Gallery chrome</button></div>
  </body>
</html>""")

            self.assertEqual(conv.detect_format(tmp), "html")
            note = conv.html_notes(tmp)[0]

            self.assertEqual(note["title"], "Recipe & Dinner")
            self.assertIn("<b>Prep:</b> 15 min", note["enml"])
            self.assertIn('<a href="https://example.com">source</a>', note["enml"])
            self.assertIn("<en-media", note["enml"])
            self.assertEqual(len(note["atts"]), 1)
            self.assertNotIn("font-family", note["enml"])
            self.assertNotIn("window.bad", note["enml"])
            self.assertNotIn("Gallery chrome", note["enml"])

            xml, resources = conv._note_to_xml(note)
            self.assertEqual(resources, 1)
            self.assertEqual(conv._integrity_bad([xml]), 0)


if __name__ == "__main__":
    unittest.main()
