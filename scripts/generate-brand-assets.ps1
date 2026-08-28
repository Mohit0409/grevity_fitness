Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

$assetRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'web\assets'
$iconRoot = Join-Path $assetRoot 'icons'
[System.IO.Directory]::CreateDirectory($iconRoot) | Out-Null

$ink = [System.Drawing.ColorTranslator]::FromHtml('#11130f')
$paper = [System.Drawing.ColorTranslator]::FromHtml('#f2f0e8')
$lime = [System.Drawing.ColorTranslator]::FromHtml('#b8ff2c')
$muted = [System.Drawing.ColorTranslator]::FromHtml('#9da397')

function New-GravityIcon([int]$size, [string]$outputName) {
    $bitmap = [System.Drawing.Bitmap]::new($size, $size)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
    $graphics.Clear($ink)
    $margin = [Math]::Max(2, [int]($size * 0.085))
    $graphics.FillRectangle([System.Drawing.SolidBrush]::new($lime), $margin, $margin, $size - (2 * $margin), $size - (2 * $margin))
    $font = [System.Drawing.Font]::new('Arial', [single]($size * 0.31), [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
    $format = [System.Drawing.StringFormat]::new()
    $format.Alignment = [System.Drawing.StringAlignment]::Center
    $format.LineAlignment = [System.Drawing.StringAlignment]::Center
    $graphics.DrawString('GF', $font, [System.Drawing.SolidBrush]::new($ink), [System.Drawing.RectangleF]::new(0, 0, $size, $size), $format)
    $bitmap.Save((Join-Path $iconRoot $outputName), [System.Drawing.Imaging.ImageFormat]::Png)
    $format.Dispose(); $font.Dispose(); $graphics.Dispose(); $bitmap.Dispose()
}

New-GravityIcon 32 'favicon-32.png'
New-GravityIcon 180 'apple-touch-icon.png'
New-GravityIcon 192 'gravity-192.png'
New-GravityIcon 512 'gravity-512.png'

$social = [System.Drawing.Bitmap]::new(1200, 630)
$canvas = [System.Drawing.Graphics]::FromImage($social)
$canvas.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$canvas.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$canvas.Clear($ink)
$gridPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(18, $paper), 1)
for ($x = 0; $x -le 1200; $x += 48) { $canvas.DrawLine($gridPen, $x, 0, $x, 630) }
for ($y = 0; $y -le 630; $y += 48) { $canvas.DrawLine($gridPen, 0, $y, 1200, $y) }
$canvas.FillRectangle([System.Drawing.SolidBrush]::new($lime), 80, 74, 88, 88)
$markFont = [System.Drawing.Font]::new('Arial', 28, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$markFormat = [System.Drawing.StringFormat]::new()
$markFormat.Alignment = [System.Drawing.StringAlignment]::Center
$markFormat.LineAlignment = [System.Drawing.StringAlignment]::Center
$canvas.DrawString('GF', $markFont, [System.Drawing.SolidBrush]::new($ink), [System.Drawing.RectangleF]::new(80, 74, 88, 88), $markFormat)
$gravityFont = [System.Drawing.Font]::new('Arial', 112, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$fitnessFont = [System.Drawing.Font]::new('Arial', 69, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$locationFont = [System.Drawing.Font]::new('Arial', 24, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$canvas.DrawString('GRAVITY', $gravityFont, [System.Drawing.SolidBrush]::new($paper), 72, 215)
$canvas.DrawString('FITNESS', $fitnessFont, [System.Drawing.SolidBrush]::new($lime), 78, 345)
$canvas.DrawString('NEEMUCH  /  MADHYA PRADESH', $locationFont, [System.Drawing.SolidBrush]::new($muted), 82, 482)
$orbitPen = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(180, $lime), 3)
$canvas.DrawEllipse($orbitPen, 724, 96, 436, 436)
$thickOrbit = [System.Drawing.Pen]::new([System.Drawing.Color]::FromArgb(45, $lime), 36)
$canvas.DrawEllipse($thickOrbit, 824, 196, 236, 236)
$hoursFont = [System.Drawing.Font]::new('Arial', 38, [System.Drawing.FontStyle]::Bold, [System.Drawing.GraphicsUnit]::Pixel)
$hoursFormat = [System.Drawing.StringFormat]::new()
$hoursFormat.Alignment = [System.Drawing.StringAlignment]::Center
$hoursFormat.LineAlignment = [System.Drawing.StringAlignment]::Center
$canvas.DrawString('06—22', $hoursFont, [System.Drawing.SolidBrush]::new($lime), [System.Drawing.RectangleF]::new(824, 196, 236, 236), $hoursFormat)
$social.Save((Join-Path $assetRoot 'og-gravity.png'), [System.Drawing.Imaging.ImageFormat]::Png)

$gridPen.Dispose(); $orbitPen.Dispose(); $thickOrbit.Dispose(); $markFont.Dispose(); $markFormat.Dispose()
$gravityFont.Dispose(); $fitnessFont.Dispose(); $locationFont.Dispose(); $hoursFont.Dispose(); $hoursFormat.Dispose()
$canvas.Dispose(); $social.Dispose()
