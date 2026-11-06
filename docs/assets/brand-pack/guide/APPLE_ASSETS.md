# iPhone and iPad app icons

Copy one icon set into your app’s Assets.xcassets and select it as App Icons Source in Xcode.

| Set | Contents |
| --- | --- |
| mobile/apple/AppIcon.appiconset | Modern Single Size: 1024-pixel Any, Dark and grayscale Tinted appearances. |
| mobile/apple/AppIcon-AllSizes.appiconset | Explicit iPhone, iPad, iPad Pro and App Store sizes. |

The Any version uses Cloud White; Dark uses Deep Slate. Both retain the original ember bird. Tinted uses the monochrome mark. All exported PNGs are unrounded RGB squares; the system supplies the icon mask. Editable SVGs and standalone 1024-pixel PNGs are in mobile/apple/masters/.

The All Sizes catalog has eighteen slots backed by thirteen PNG dimensions, including the 167-pixel iPad Pro icon. Point sizes and scale factors are recorded in Contents.json. Choose one catalog for the target, then review its appearances in Xcode and on the intended devices before release.

The pack supplies flat app-icon artwork and asset-catalog inputs. Layered Icon Composer projects can be built from the vector masters separately.

Sources: [Apple asset-catalog configuration](https://developer.apple.com/documentation/xcode/configuring-your-app-icon) and [App Icon Type reference](https://developer.apple.com/library/archive/documentation/Xcode/Reference/xcode_ref-Asset_Catalog_Format/AppIconType.html).
