import QtQuick
import Quickshell
import Quickshell.Wayland
import Quickshell.Services.Pam
import qs.services
import qs.components

// The lock screen (Super+X): the garden at night, the time, Pasha keeping watch, and a password
// plate. Checked by PAM, as your login is.
Scope {
	id: root
	property bool locked: false
	function lock() { locked = true }

	PamContext {
		id: pam
		config: "login"
		onCompleted: result => {
			if (result === PamResult.Success) {
				root.locked = false
				root.failed = false
			} else {
				root.failed = true
			}
			root.password = ""
		}
		onResponseRequiredChanged: if (responseRequired && root.password !== "") respond(root.password)
	}
	property string password: ""
	property bool failed: false
	function tryUnlock() {
		if (password === "" || pam.active) return
		pam.start()   // PAM then asks for the password: onResponseRequiredChanged answers
	}

	SystemClock { id: clock; precision: SystemClock.Seconds }

	WlSessionLock {
		locked: root.locked
		WlSessionLockSurface {
			color: Theme.night

			Image {
				anchors.fill: parent
				// the default built into your stick, if there is one, else the garden
				source: "file:///usr/share/avalon/local-wallpaper.png"
				onStatusChanged: if (status === Image.Error) source = "file:///usr/share/avalon/garden-wallpaper.png"
				smooth: false                 // hard pixels, as the garden is drawn
				fillMode: Image.PreserveAspectCrop
				opacity: 0.45
			}
			Rectangle { anchors.fill: parent; color: "#80030610" }

			Column {
				anchors.centerIn: parent
				spacing: 18

				Text {
					anchors.horizontalCenter: parent.horizontalCenter
					text: Qt.formatTime(clock.date, "HH:mm")
					color: Theme.text
					font.family: Theme.fontMono
					font.pixelSize: 96
					font.bold: true
					style: Text.Outline
					styleColor: "#30" + Theme.cyan.toString().slice(1)
				}
				Text {
					anchors.horizontalCenter: parent.horizontalCenter
					text: Qt.formatDate(clock.date, "dddd d MMMM").toUpperCase()
					color: Theme.ice
					font.family: Theme.font
					font.pixelSize: Theme.normal
					font.letterSpacing: 4
				}
				Image {
					anchors.horizontalCenter: parent.horizontalCenter
					source: "file:///usr/share/avalon/pasha-portrait.png"
					width: 150; height: 150
					fillMode: Image.PreserveAspectFit
				}
				HudPanel {
					anchors.horizontalCenter: parent.horizontalCenter
					width: 360; height: 48
					glow: field.activeFocus
					stroke: root.failed ? Theme.magenta : Theme.edge
					TextInput {
						id: field
						anchors.fill: parent
						verticalAlignment: TextInput.AlignVCenter
						horizontalAlignment: TextInput.AlignHCenter
						echoMode: TextInput.Password
						passwordCharacter: "◆"
						color: Theme.cyan
						font.pixelSize: Theme.large
						focus: true
						onTextChanged: { root.password = text; if (text !== "") root.failed = false }
						Connections {   // cleared after each try
							target: root
							function onPasswordChanged() { if (root.password === "") field.text = "" }
						}
						Keys.onReturnPressed: root.tryUnlock()
						Keys.onEnterPressed: root.tryUnlock()
					}
				}
				Text {
					anchors.horizontalCenter: parent.horizontalCenter
					text: root.failed ? "Pasha doesn't know that one. Try again." : "Pasha is keeping watch"
					color: root.failed ? Theme.magenta : Theme.textDim
					font.family: Theme.font
					font.pixelSize: Theme.small
				}
			}
		}
	}
}
