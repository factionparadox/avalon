import QtQuick
import QtQuick.Shapes
import Quickshell
import Quickshell.Services.Greetd

// The Garden System's login screen, run by greetd in cage:
//   cage -s -- quickshell -p /usr/share/garden/greeter.qml
// Name, then password, then Avalon's session (Mango). Self-contained: it runs as the greeter
// user, before anyone's settings exist.
ShellRoot {
	id: root
	readonly property color night: "#070b16"
	readonly property color panel: "#d90c1426"
	readonly property color edge: "#3a5a8c"
	readonly property color cyan: "#5fd8f0"
	readonly property color magenta: "#ff3fa4"
	readonly property color mint: "#bfe3d6"
	readonly property color text: "#eef4fb"
	readonly property color dim: "#8fa0bf"
	readonly property string font: "DejaVu Sans"

	property string stage: "user"      // user → password → starting
	property string message: ""
	property bool error: false
	property string pendingPassword: ""

	function submit(value) {
		if (stage === "user") {
			if (value === "") return
			message = ""; error = false
			Greetd.createSession(value)
			stage = "password"
		} else if (stage === "password") {
			pendingPassword = value
			Greetd.respond(value)
		}
	}

	Connections {
		target: Greetd
		function onAuthMessage(msg, isError, responseRequired, echoResponse) {
			root.message = msg
			root.error = isError
		}
		function onAuthFailure(msg) {
			root.message = "Pasha doesn't know that one. Try again."
			root.error = true
			root.stage = "user"
			field.text = ""
		}
		function onReadyToLaunch() {
			root.stage = "starting"
			root.message = "Opening the garden…"
			Greetd.launch(["mango"], ["XDG_SESSION_TYPE=wayland", "XDG_CURRENT_DESKTOP=mango"])
		}
		function onError(err) {
			root.message = "greetd: " + err
			root.error = true
			root.stage = "user"
		}
	}

	FloatingWindow {
		color: root.night
		visible: true

		Image {
			anchors.fill: parent
			// the default built into your stick, if there is one, else the garden
			source: "file:///usr/share/avalon/local-wallpaper.png"
			onStatusChanged: if (status === Image.Error) source = "file:///usr/share/avalon/garden-wallpaper.png"
			smooth: false                 // hard pixels, as the garden is drawn
			fillMode: Image.PreserveAspectCrop
		}
		Rectangle { anchors.fill: parent; color: "#60030610" }

		Column {
			anchors.centerIn: parent
			spacing: 16

			// Pasha in his spotlight
			Item {
				anchors.horizontalCenter: parent.horizontalCenter
				width: 240; height: 240
				Rectangle {
					width: 200; height: 44; radius: 22
					anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom }
					gradient: Gradient {
						orientation: Gradient.Horizontal
						GradientStop { position: 0; color: "transparent" }
						GradientStop { position: 0.5; color: "#c05fd8f0" }
						GradientStop { position: 1; color: "transparent" }
					}
				}
				Image {
					anchors { horizontalCenter: parent.horizontalCenter; bottom: parent.bottom; bottomMargin: 16 }
					source: "file:///usr/share/avalon/pasha-portrait.png"
					width: 210; height: 210
					fillMode: Image.PreserveAspectFit
				}
			}

			Text {
				anchors.horizontalCenter: parent.horizontalCenter
				text: "AVALON"
				color: root.text
				font.family: root.font
				font.pixelSize: 30
				font.bold: true
				font.letterSpacing: 10
			}

			// the plate: a cut-corner HUD box
			Item {
				anchors.horizontalCenter: parent.horizontalCenter
				width: 380; height: 52
				Shape {
					anchors.fill: parent
					preferredRendererType: Shape.CurveRenderer
					ShapePath {
						fillColor: root.panel
						strokeColor: root.error ? root.magenta : field.activeFocus ? root.cyan : root.edge
						strokeWidth: 1.5
						startX: 12; startY: 0
						PathLine { x: 380; y: 0 }
						PathLine { x: 380; y: 40 }
						PathLine { x: 368; y: 52 }
						PathLine { x: 0; y: 52 }
						PathLine { x: 0; y: 12 }
						PathLine { x: 12; y: 0 }
					}
				}
				TextInput {
					id: field
					anchors.fill: parent
					anchors.margins: 12
					verticalAlignment: TextInput.AlignVCenter
					horizontalAlignment: TextInput.AlignHCenter
					color: root.stage === "password" ? root.cyan : root.text
					echoMode: root.stage === "password" ? TextInput.Password : TextInput.Normal
					passwordCharacter: "◆"
					font.family: root.font
					font.pixelSize: 18
					focus: true
					enabled: root.stage !== "starting"
					Text {
						anchors.centerIn: parent
						visible: field.text === ""
						text: root.stage === "user" ? "name" : root.stage === "password" ? "password" : ""
						color: root.dim
						font: field.font
					}
					Keys.onReturnPressed: { const v = text; text = ""; root.submit(v) }
					Keys.onEnterPressed: { const v = text; text = ""; root.submit(v) }
					Keys.onEscapePressed: { Greetd.cancelSession(); root.stage = "user"; text = ""; root.message = "" }
				}
			}

			Text {
				anchors.horizontalCenter: parent.horizontalCenter
				text: root.message
				color: root.error ? root.magenta : root.dim
				font.family: root.font
				font.pixelSize: 13
			}
		}
	}
}
