// Standalone WAV experiment. No microphone, permission request, asset download,
// network fallback, or Motive linkage. Compile only for explicit offline tests.
import Foundation
import Speech

func emit(_ value: [String: Any]) {
    let data = try! JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    print(String(data: data, encoding: .utf8)!)
}

let arguments = CommandLine.arguments
guard arguments.count == 2 || arguments.count == 3 else {
    emit(["status": "BLOCKED", "code": "invalid_arguments", "usage": "voice-apple-offline --probe | file.wav [es-MX]"])
    exit(2)
}
let locale = arguments.count == 3 ? arguments[2] : "es-MX"
let authorization = SFSpeechRecognizer.authorizationStatus()
let authorizationName: String
switch authorization {
case .authorized: authorizationName = "authorized"
case .denied: authorizationName = "denied"
case .restricted: authorizationName = "restricted"
case .notDetermined: authorizationName = "not_determined"
@unknown default: authorizationName = "unknown"
}
// Checking authorization never requests it. Do not instantiate a recognition
// request when this executable lacks the existing permission.
guard authorization == .authorized else {
    emit(["status": "BLOCKED", "code": "speech_permission_not_authorized",
          "authorization": authorizationName, "requested_permission": false,
          "locale": locale, "network_fallback": false])
    exit(3)
}
guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: locale)) else {
    emit(["status": "BLOCKED", "code": "locale_unavailable", "locale": locale])
    exit(3)
}
guard recognizer.supportsOnDeviceRecognition else {
    emit(["status": "BLOCKED", "code": "on_device_unavailable", "locale": locale,
          "network_fallback": false, "requested_asset_download": false])
    exit(3)
}
guard recognizer.isAvailable else {
    emit(["status": "BLOCKED", "code": "recognizer_unavailable", "locale": locale])
    exit(3)
}
if arguments[1] == "--probe" {
    emit(["status": "PASS", "scope": "availability_only", "authorization": authorizationName,
          "locale": locale, "supports_on_device": true, "recognition_started": false])
    exit(0)
}
let file = URL(fileURLWithPath: arguments[1])
guard FileManager.default.fileExists(atPath: file.path), file.pathExtension.lowercased() == "wav" else {
    emit(["status": "BLOCKED", "code": "wav_missing"])
    exit(2)
}
let request = SFSpeechURLRecognitionRequest(url: file)
request.requiresOnDeviceRecognition = true
request.shouldReportPartialResults = false
request.taskHint = .dictation
recognizer.queue = OperationQueue.main
let start = ProcessInfo.processInfo.systemUptime
var finished = false
var succeeded = false
let task = recognizer.recognitionTask(with: request) { result, error in
    if finished { return }
    if let result = result, result.isFinal {
        succeeded = true
        finished = true
        emit(["status": "PASS", "scope": "offline_wav", "locale": locale,
              "on_device_required": true, "text": result.bestTranscription.formattedString,
              "wall_ms": (ProcessInfo.processInfo.systemUptime - start) * 1000,
              "segments": result.bestTranscription.segments.map {
                  ["text": $0.substring, "start_seconds": $0.timestamp,
                   "duration_seconds": $0.duration, "confidence": $0.confidence] as [String: Any]
              }])
    } else if let error = error {
        finished = true
        let nsError = error as NSError
        emit(["status": "BLOCKED", "code": "recognition_error", "domain": nsError.domain,
              "error_code": nsError.code, "on_device_required": true])
    }
}
while !finished && ProcessInfo.processInfo.systemUptime - start < 60 {
    RunLoop.current.run(until: Date(timeIntervalSinceNow: 0.05))
}
if !finished {
    finished = true
    task.cancel()
    emit(["status": "BLOCKED", "code": "recognition_timeout", "timeout_seconds": 60])
}
exit(succeeded ? 0 : 3)
