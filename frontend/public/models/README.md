# 3D Avatar Models

Place your `.glb` model file here and name it `avatar.glb`.

The avatar component will automatically load the model from `/models/avatar.glb`.

## Model Requirements

- Format: GLB (binary GLTF)
- Should include morph targets (blend shapes) for mouth animation
- Common mouth morph target names: `mouthOpen`, `Mouth_Open`, `mouth_open`, `jawOpen`, `Jaw_Open`

## Free 3D Avatar Resources

- [Ready Player Me](https://readyplayer.me/) - Create free 3D avatars
- [VRoid Hub](https://hub.vroid.com/) - 3D character models
- [Sketchfab](https://sketchfab.com/) - 3D models marketplace (many free)
- [Mixamo](https://www.mixamo.com/) - Free 3D characters and animations

## Exporting from Blender

1. Model your character
2. Add shape keys (morph targets) for mouth animation
3. Export as GLB format
4. Place in this directory as `avatar.glb`

If no model is provided, a simple placeholder avatar will be displayed.

