from http.server import BaseHTTPRequestHandler, HTTPServer

HTML_PAGE = """
<html>
  <body>
    <table>
      <tr><td>1</td><td>PAC</td><td>:</td><td>4500</td></tr>
      <tr><td>2</td><td>PACL1</td><td>:</td><td>1500</td></tr>
      <tr><td>3</td><td>PACL2</td><td>:</td><td>1500</td></tr>
      <tr><td>4</td><td>PACL3</td><td>:</td><td>1500</td></tr>
      <tr><td>5</td><td>UDC1</td><td>:</td><td>380</td></tr>
      <tr><td>6</td><td>UDC2</td><td>:</td><td>375</td></tr>
      <tr><td>7</td><td>UDC3</td><td>:</td><td>370</td></tr>
      <tr><td>8</td><td>IDC1</td><td>:</td><td>8.2</td></tr>
      <tr><td>9</td><td>IDC2</td><td>:</td><td>8.3</td></tr>
      <tr><td>10</td><td>IDC3</td><td>:</td><td>8.4</td></tr>
      <tr><td>11</td><td>ET</td><td>:</td><td>12.5</td></tr>
      <tr><td>12</td><td>EG</td><td>:</td><td>5200</td></tr>
      <tr><td>13</td><td>ETA</td><td>:</td><td>96.3</td></tr>
    </table>
  </body>
</html>
"""

class FakeSolutronicHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/solutronic/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode("utf-8"))
        else:
            self.send_error(404)

if __name__ == "__main__":
    server_address = ("0.0.0.0", 8888)
    httpd = HTTPServer(server_address, FakeSolutronicHandler)
    print("Fake Solutronic server running on port 8888...")
    httpd.serve_forever()