// Original asset renderer, GPL-3.0-or-later. AppKit is used offline; no capture.
import AppKit
import Foundation
let args = CommandLine.arguments
let input = URL(fileURLWithPath: args[1])
let data = try Data(contentsOf: input)
let jobs = try JSONSerialization.jsonObject(with: data) as! [[String: Any]]
func num(_ d: [String:Any], _ k: String, _ fallback: Double = 0) -> CGFloat { CGFloat((d[k] as? NSNumber)?.doubleValue ?? fallback) }
func color(_ s: String, _ alpha: CGFloat = 1) -> NSColor {
 let v = UInt64(s.replacingOccurrences(of:"#",with:""),radix:16) ?? 0
 return NSColor(srgbRed: CGFloat((v>>16)&255)/255, green: CGFloat((v>>8)&255)/255, blue: CGFloat(v&255)/255, alpha:alpha)
}
for job in jobs {
 let width = Int(num(job,"width")), height = Int(num(job,"height"))
 let rep = NSBitmapImageRep(bitmapDataPlanes:nil,pixelsWide:width,pixelsHigh:height,bitsPerSample:8,samplesPerPixel:4,hasAlpha:true,isPlanar:false,colorSpaceName:.deviceRGB,bytesPerRow:0,bitsPerPixel:0)!
 let graphics = NSGraphicsContext(bitmapImageRep:rep)!
 NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current = graphics
 let ctx = graphics.cgContext
 ctx.clear(CGRect(x:0,y:0,width:width,height:height))
 ctx.translateBy(x:0,y:CGFloat(height));ctx.scaleBy(x:1,y:-1)
 for node in job["nodes"] as! [[String:Any]] {
  ctx.saveGState();ctx.setAlpha(num(node,"opacity",1))
  let kind=node["kind"] as! String
  if kind == "image" {
   let url=URL(fileURLWithPath:node["path"] as! String)
   if let src=CGImageSourceCreateWithURL(url as CFURL,nil),let image=CGImageSourceCreateImageAtIndex(src,0,nil) {
    ctx.translateBy(x:num(node,"x"),y:num(node,"y")+num(node,"height"));ctx.scaleBy(x:1,y:-1)
    ctx.draw(image,in:CGRect(x:0,y:0,width:num(node,"width"),height:num(node,"height")))
   }
  } else if kind == "text" {
   let text=node["text"] as! String, size=num(node,"size",24)
   let font=NSFont(name:node["font"] as? String ?? "Helvetica",size:size) ?? NSFont.systemFont(ofSize:size)
   let attrs:[NSAttributedString.Key:Any]=[.font:font,.foregroundColor:color(node["fill"] as? String ?? "#ffffff")]
   let str=NSAttributedString(string:text,attributes:attrs)
   // AppKit text draws into a flipped context; explicit baseline is top + ascender.
   let line=CTLineCreateWithAttributedString(str)
   ctx.textMatrix=CGAffineTransform(scaleX:1,y:-1)
   ctx.textPosition=CGPoint(x:num(node,"x"),y:num(node,"y")+font.ascender)
   CTLineDraw(line,ctx)
  } else {
   let path=CGMutablePath()
   if kind == "rect" { path.addRect(CGRect(x:num(node,"x"),y:num(node,"y"),width:num(node,"width"),height:num(node,"height"))) }
   else if kind == "ellipse" { path.addEllipse(in:CGRect(x:num(node,"x"),y:num(node,"y"),width:num(node,"width"),height:num(node,"height"))) }
   else if kind == "poly" {
    let pts=node["points"] as! [[Double]]
    if let p=pts.first {path.move(to:CGPoint(x:p[0],y:p[1]))}
    for p in pts.dropFirst(){path.addLine(to:CGPoint(x:p[0],y:p[1]))}
    if node["closed"] as? Bool ?? false {path.closeSubpath()}
   }
   if let fill=node["fill"] as? String,fill != "none" {ctx.addPath(path);ctx.setFillColor(color(fill).cgColor);ctx.fillPath()}
   if let stroke=node["stroke"] as? String,stroke != "none" {ctx.addPath(path);ctx.setStrokeColor(color(stroke).cgColor);ctx.setLineWidth(num(node,"stroke_width",1));ctx.setLineJoin(.miter);ctx.strokePath()}
  }
  ctx.restoreGState()
 }
 NSGraphicsContext.restoreGraphicsState()
 let png=rep.representation(using:.png,properties:[:])!
 try png.write(to:URL(fileURLWithPath:job["output"] as! String))
 print("Rendered \(URL(fileURLWithPath:job["output"] as! String).lastPathComponent) \(width)x\(height)")
}
