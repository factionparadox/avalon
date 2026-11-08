import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.services

// The garden itself, behind every window: Avalon's wallpaper on each screen.
Variants {
	model: Quickshell.screens
	delegate: Component {
		PanelWindow {
			required property var modelData
			screen: modelData
			anchors { top: true; bottom: true; left: true; right: true }
			exclusionMode: ExclusionMode.Ignore
			color: Theme.night
			WlrLayershell.layer: WlrLayer.Background
			WlrLayershell.namespace: "garden-wallpaper"

			Image {
				anchors.fill: parent
				// your own picture (Avalon Control links it here), else the default built into
				// your stick (local-wallpaper.png, if there is one), else the garden
				readonly property var choices: [
					"file://" + Quickshell.env("HOME") + "/.config/avalon/wallpaper",
					"file:///usr/share/avalon/local-wallpaper.png",
					"file:///usr/share/avalon/garden-wallpaper.png"
				]
				property int choice: 0
				source: choices[choice]
				onStatusChanged: if (status === Image.Error && choice < choices.length - 1) choice++
				fillMode: Image.PreserveAspectCrop
				asynchronous: true
				smooth: choice === 0          // a photo of yours smooth; the others in hard pixels
			}
		}
	}
}
