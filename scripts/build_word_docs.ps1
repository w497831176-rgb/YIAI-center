param(
    [Parameter(Mandatory = $true)][string]$MarkdownPath,
    [Parameter(Mandatory = $true)][string]$TemplatePath,
    [Parameter(Mandatory = $true)][string]$OutputPath
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$source = (Resolve-Path -LiteralPath $MarkdownPath).Path
$template = (Resolve-Path -LiteralPath $TemplatePath).Path
$destination = [System.IO.Path]::GetFullPath($OutputPath)

if ($template -ne $destination) {
    Copy-Item -LiteralPath $template -Destination $destination -Force
}

function Escape-Xml([string]$Text) {
    if ($null -eq $Text) { return '' }
    return [System.Security.SecurityElement]::Escape($Text)
}

function New-Paragraph([string]$Text, [string]$Style = '') {
    $escaped = Escape-Xml $Text
    $properties = if ($Style) { "<w:pPr><w:pStyle w:val=`"$Style`"/></w:pPr>" } else { '' }
    return "<w:p>$properties<w:r><w:t xml:space=`"preserve`">$escaped</w:t></w:r></w:p>"
}

$paragraphs = [System.Collections.Generic.List[string]]::new()
$inCode = $false
foreach ($line in [System.IO.File]::ReadAllLines($source, [System.Text.Encoding]::UTF8)) {
    if ($line.StartsWith('```')) {
        $inCode = -not $inCode
        continue
    }
    if ($inCode) {
        $paragraphs.Add((New-Paragraph $line 'Code'))
        continue
    }
    if ($line.StartsWith('# ')) {
        $paragraphs.Add((New-Paragraph $line.Substring(2) 'Title'))
    } elseif ($line.StartsWith('## ')) {
        $paragraphs.Add((New-Paragraph $line.Substring(3) 'Heading1'))
    } elseif ($line.StartsWith('### ')) {
        $paragraphs.Add((New-Paragraph $line.Substring(4) 'Heading2'))
    } elseif ($line.StartsWith('#### ')) {
        $paragraphs.Add((New-Paragraph $line.Substring(5) 'Heading3'))
    } elseif ($line.StartsWith('- ')) {
        $paragraphs.Add((New-Paragraph ('• ' + $line.Substring(2)) 'ListParagraph'))
    } elseif ($line -match '^\d+\. ') {
        $paragraphs.Add((New-Paragraph $line 'ListParagraph'))
    } elseif ($line.StartsWith('> ')) {
        $paragraphs.Add((New-Paragraph $line.Substring(2) 'Quote'))
    } elseif ($line -eq '---') {
        continue
    } else {
        $paragraphs.Add((New-Paragraph $line))
    }
}

$documentXml = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    $($paragraphs -join "`n    ")
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>
"@

$archive = [System.IO.Compression.ZipFile]::Open($destination, [System.IO.Compression.ZipArchiveMode]::Update)
try {
    $oldEntry = $archive.GetEntry('word/document.xml')
    if ($null -ne $oldEntry) { $oldEntry.Delete() }
    $entry = $archive.CreateEntry('word/document.xml', [System.IO.Compression.CompressionLevel]::Optimal)
    $stream = $entry.Open()
    try {
        $utf8 = [System.Text.UTF8Encoding]::new($false)
        $bytes = $utf8.GetBytes($documentXml)
        $stream.Write($bytes, 0, $bytes.Length)
    } finally {
        $stream.Dispose()
    }
} finally {
    $archive.Dispose()
}

Write-Output $destination
