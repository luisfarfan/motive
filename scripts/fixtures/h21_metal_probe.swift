// Read-only resource probe corresponding to OBS 33.0.1 MetalDevice.init steps.
// No capture, window, audio, display-mode, preference or permission mutations.
import Foundation
import Metal
import CoreVideo

var report: [String: Any] = ["scope": "standalone prerequisite probe; not a Motive acceptance run"]
if let device = MTLCreateSystemDefaultDevice() {
    report["metal_device"] = true
    let queue = device.makeCommandQueue()
    report["command_queue"] = queue != nil
    let buffer = device.makeBuffer(length: 1, options: .storageModePrivate)
    report["private_buffer"] = buffer != nil
    let options = MTLCompileOptions()
    options.mathMode = .fast
    do {
        let library = try device.makeLibrary(source: "[[vertex]] float4 vsNop() { return (float4)0; }", options: options)
        report["nop_vertex_function"] = library.makeFunction(name: "vsNop") != nil
    } catch {
        let value = error as NSError
        report["shader_error"] = ["domain": value.domain, "code": value.code]
    }
    var link: CVDisplayLink?
    report["display_link_result"] = CVDisplayLinkCreateWithActiveCGDisplays(&link)
    report["display_link"] = link != nil
} else {
    report["metal_device"] = false
}
let data = try JSONSerialization.data(withJSONObject: report, options: [.prettyPrinted, .sortedKeys])
FileHandle.standardOutput.write(data)
FileHandle.standardOutput.write(Data([10]))
