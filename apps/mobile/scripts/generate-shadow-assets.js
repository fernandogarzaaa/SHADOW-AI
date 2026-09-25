/* One-off SHADOW asset generator. Run: node scripts/generate-shadow-assets.js */
const path = require("path");
const sharp = require("sharp");

const ASSETS = path.join(__dirname, "..", "assets");
const BG = "#0A0A0A";
const GLYPH = "#B9B9B9";
const GLYPH_DIM = "#6E6E6E";

function svgSquare(size, glyphColor, glyphSize, glyphOpacity = 1) {
	return Buffer.from(`
<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" xmlns="http://www.w3.org/2000/svg">
  <rect width="${size}" height="${size}" rx="${Math.round(size * 0.22)}" fill="${BG}"/>
  <text x="${size / 2}" y="${size / 2}" text-anchor="middle" dominant-baseline="central"
        font-family="DejaVu Sans, sans-serif" font-weight="bold" font-size="${glyphSize}"
        fill="${glyphColor}" opacity="${glyphOpacity}">S</text>
</svg>`);
}

function svgSplash(w, h) {
	return Buffer.from(`
<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
  <rect width="${w}" height="${h}" fill="${BG}"/>
  <text x="${w / 2}" y="${h / 2}" text-anchor="middle" dominant-baseline="central"
        font-family="DejaVu Sans, sans-serif" font-weight="bold" font-size="420"
        fill="${GLYPH_DIM}" opacity="0.9">S</text>
</svg>`);
}

function svgNotificationGlyph(size) {
	return Buffer.from(`
<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" xmlns="http://www.w3.org/2000/svg">
  <text x="${size / 2}" y="${size / 2}" text-anchor="middle" dominant-baseline="central"
        font-family="DejaVu Sans, sans-serif" font-weight="bold" font-size="${Math.round(size * 0.72)}"
        fill="#FFFFFF">S</text>
</svg>`);
}

async function main() {
	await sharp(svgSquare(1024, GLYPH, 560)).png().toFile(path.join(ASSETS, "icon.png"));
	await sharp(svgSquare(1024, GLYPH, 560)).png().toFile(path.join(ASSETS, "adaptive-icon.png"));
	await sharp(svgSplash(1284, 2778)).png().toFile(path.join(ASSETS, "splash.png"));
	await sharp(svgNotificationGlyph(96)).png().toFile(path.join(ASSETS, "notification-icon.png"));
	await sharp(svgSquare(64, GLYPH, 36)).png().toFile(path.join(ASSETS, "favicon.png"));
	console.log("assets written");
}

main().catch((err) => {
	console.error(err);
	process.exit(1);
});
