# Android phone and tablet icons

The same Android resources support phone and tablet launchers. Copy mobile/android/res/ into the chosen app’s resource source set, merging existing resource names carefully.

```xml
<application android:icon="@mipmap/ic_launcher"
             android:roundIcon="@mipmap/ic_launcher_round" />
```

The adaptive set contains separate 108-dp foreground/background vectors and a monochrome layer for themed icons. The complete bird fits the central 66-dp safe region. API-26 resource definitions select the colour artwork; API-33 definitions also expose the monochrome layer. Use compileSdk 33 or later.

| Asset | Location |
| --- | --- |
| Native foreground and background | res/drawable-v26/ |
| Native monochrome | res/drawable-v33/ |
| Adaptive definitions | res/mipmap-anydpi-v26/ and res/mipmap-anydpi-v33/ |
| Legacy square/round PNGs | res/mipmap-mdpi/ through res/mipmap-xxxhdpi/ |
| Play listing icon | bifang-google-play-512.png |
| Editable vectors and mask previews | mobile/android/ |

Legacy exports cover 48, 72, 96, 144 and 192 pixels. The Play icon is a full-square 512-pixel sRGB RGBA PNG. Keep that unrounded source; Play supplies its own mask and shadow.

Circle, squircle and rounded-square previews help inspect the mark under different masks. The safe-area diagram is a guide. Review actual launcher appearances after integration.

Sources: [Android adaptive icons](https://developer.android.com/develop/ui/compose/system/icon_design_adaptive), [VectorDrawable](https://developer.android.com/reference/android/graphics/drawable/VectorDrawable) and [Play icon specifications](https://developer.android.com/distribute/google-play/resources/icon-design-specifications).
