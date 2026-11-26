// Cuts what stands out in a picture with the system's own subject lifting (macOS 14 or later) and writes it white on
// black at the picture's size, for stage.py.
//   usage: swift lift.swift picture.jpg mask.png
import CoreImage
import Foundation
import ImageIO
import UniformTypeIdentifiers
import Vision

let args = CommandLine.arguments
guard args.count == 3, let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: args[1]) as CFURL, nil),
      let picture = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
  fatalError("usage: swift lift.swift picture.jpg mask.png")
}
let handler = VNImageRequestHandler(cgImage: picture)
let request = VNGenerateForegroundInstanceMaskRequest()
try handler.perform([request])
guard let found = request.results?.first else { fatalError("nothing stands out") }
let mask = CIImage(cvPixelBuffer: try found.generateScaledMaskForImage(forInstances: found.allInstances, from: handler))
guard let image = CIContext().createCGImage(mask, from: mask.extent),
      let out = CGImageDestinationCreateWithURL(URL(fileURLWithPath: args[2]) as CFURL, UTType.png.identifier as CFString, 1, nil) else {
  fatalError("cannot write \(args[2])")
}
CGImageDestinationAddImage(out, image, nil)
CGImageDestinationFinalize(out)
