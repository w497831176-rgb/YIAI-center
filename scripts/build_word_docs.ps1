param(
    [Parameter(Mandatory = $true)]
    [string]$MarkdownPath,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [Parameter(Mandatory = $false)]
    [string]$TemplatePath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

function Escape-Xml {
    param([string]$Value)
    if ($null -eq $Value) { return '' }
    return [System.Security.SecurityElement]::Escape($Value)
}

function Clean-InlineMarkdown {
    param([string]$Value)
    $clean = $Value.Replace('**', '').Replace('__', '').Replace('`', '')
    $clean = $clean.Replace('<br>', ' ').Replace('<br/>', ' ').Replace('<br />', ' ')
    return $clean.TrimEnd()
}

function New-RunXml {
    param(
        [string]$Text,
        [switch]$Bold
    )

    $escaped = Escape-Xml (Clean-InlineMarkdown $Text)
    $boldXml = if ($Bold) { '<w:b/><w:bCs/>' } else { '' }
    return "<w:r><w:rPr><w:rFonts w:ascii=`"Microsoft YaHei`" w:hAnsi=`"Microsoft YaHei`" w:eastAsia=`"Microsoft YaHei`" w:cs=`"Microsoft YaHei`"/>$boldXml<w:lang w:val=`"zh-CN`" w:eastAsia=`"zh-CN`"/></w:rPr><w:t xml:space=`"preserve`">$escaped</w:t></w:r>"
}

function New-ParagraphXml {
    param(
        [string]$Text,
        [string]$StyleId = 'Normal',
        [switch]$Bold
    )

    if ([string]::IsNullOrEmpty($Text)) {
        return '<w:p/>'
    }

    $run = New-RunXml -Text $Text -Bold:$Bold
    return "<w:p><w:pPr><w:pStyle w:val=`"$StyleId`"/></w:pPr>$run</w:p>"
}

function Convert-MarkdownToDocumentXml {
    param([string]$Markdown)

    $paragraphs = [System.Collections.Generic.List[string]]::new()
    $insideCode = $false
    $seenTitle = $false

    foreach ($rawLine in ($Markdown -split "`r?`n", 0, 'RegexMatch')) {
        $line = $rawLine.TrimEnd()

        if ($line -match '^\s*```') {
            $insideCode = -not $insideCode
            continue
        }

        if ($insideCode) {
            $paragraphs.Add((New-ParagraphXml -Text $line -StyleId 'Code'))
            continue
        }

        if ($line -match '^#\s+(.+)$') {
            if (-not $seenTitle) {
                $paragraphs.Add((New-ParagraphXml -Text $matches[1] -StyleId 'Title' -Bold))
                $seenTitle = $true
            }
            else {
                $paragraphs.Add((New-ParagraphXml -Text $matches[1] -StyleId 'Heading1' -Bold))
            }
            continue
        }

        if ($line -match '^##\s+(.+)$') {
            $paragraphs.Add((New-ParagraphXml -Text $matches[1] -StyleId 'Heading1' -Bold))
            continue
        }

        if ($line -match '^###\s+(.+)$') {
            $paragraphs.Add((New-ParagraphXml -Text $matches[1] -StyleId 'Heading2' -Bold))
            continue
        }

        if ($line -match '^####\s+(.+)$') {
            $paragraphs.Add((New-ParagraphXml -Text $matches[1] -StyleId 'Heading3' -Bold))
            continue
        }

        if ($line -match '^>\s?(.*)$') {
            $paragraphs.Add((New-ParagraphXml -Text $matches[1] -StyleId 'Quote'))
            continue
        }

        if ($line -match '^\s*-\s+(.+)$') {
            $paragraphs.Add((New-ParagraphXml -Text ("- " + $matches[1]) -StyleId 'ListParagraph'))
            continue
        }

        if ($line -match '^\s*(\d+\.)\s+(.+)$') {
            $paragraphs.Add((New-ParagraphXml -Text ($matches[1] + ' ' + $matches[2]) -StyleId 'ListParagraph'))
            continue
        }

        if ($line -match '^\s*\|?\s*:?-{3,}') {
            continue
        }

        if ($line -match '^\s*---+\s*$') {
            continue
        }

        if ($line -match '^\s*\|(.+)\|\s*$') {
            $cells = $matches[1].Split('|') | ForEach-Object { $_.Trim() }
            $paragraphs.Add((New-ParagraphXml -Text ($cells -join '    |    ') -StyleId 'TableText'))
            continue
        }

        $paragraphs.Add((New-ParagraphXml -Text $line -StyleId 'Normal'))
    }

    $body = $paragraphs -join ''
    return @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    $body
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="567" w:footer="567" w:gutter="0"/>
      <w:cols w:space="425"/>
    </w:sectPr>
  </w:body>
</w:document>
"@
}

function Add-ZipTextEntry {
    param(
        [System.IO.Compression.ZipArchive]$Archive,
        [string]$EntryName,
        [string]$Content
    )

    $entry = $Archive.CreateEntry($EntryName, [System.IO.Compression.CompressionLevel]::Optimal)
    $stream = $entry.Open()
    try {
        $writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
        try {
            $writer.Write($Content)
        }
        finally {
            $writer.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

$markdownFullPath = (Resolve-Path -LiteralPath $MarkdownPath).Path
$markdown = [System.IO.File]::ReadAllText($markdownFullPath, [System.Text.Encoding]::UTF8)
$documentXml = Convert-MarkdownToDocumentXml -Markdown $markdown
$outputFullPath = [System.IO.Path]::GetFullPath($OutputPath)
$outputDirectory = [System.IO.Path]::GetDirectoryName($outputFullPath)
[System.IO.Directory]::CreateDirectory($outputDirectory) | Out-Null
$temporaryPath = $outputFullPath + '.rebuild.tmp'

if ([System.IO.File]::Exists($temporaryPath)) {
    [System.IO.File]::Delete($temporaryPath)
}

$stylesXml = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:docDefaults>
    <w:rPrDefault><w:rPr><w:rFonts w:ascii="Microsoft YaHei" w:hAnsi="Microsoft YaHei" w:eastAsia="Microsoft YaHei" w:cs="Microsoft YaHei"/><w:sz w:val="22"/><w:szCs w:val="22"/><w:lang w:val="zh-CN" w:eastAsia="zh-CN"/></w:rPr></w:rPrDefault>
    <w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="360" w:lineRule="auto"/></w:pPr></w:pPrDefault>
  </w:docDefaults>
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:after="120" w:line="360" w:lineRule="auto"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:spacing w:before="0" w:after="300"/><w:jc w:val="center"/></w:pPr><w:rPr><w:b/><w:bCs/><w:color w:val="1F4E78"/><w:sz w:val="34"/><w:szCs w:val="34"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="Heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="280" w:after="140"/></w:pPr><w:rPr><w:b/><w:bCs/><w:color w:val="1F4E78"/><w:sz w:val="28"/><w:szCs w:val="28"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="Heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="220" w:after="100"/></w:pPr><w:rPr><w:b/><w:bCs/><w:color w:val="2F5597"/><w:sz w:val="24"/><w:szCs w:val="24"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="Heading 3"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:qFormat/><w:pPr><w:keepNext/><w:spacing w:before="180" w:after="80"/></w:pPr><w:rPr><w:b/><w:bCs/><w:color w:val="44546A"/><w:sz w:val="22"/><w:szCs w:val="22"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="420" w:hanging="210"/><w:spacing w:after="80"/></w:pPr></w:style>
  <w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="420"/><w:spacing w:after="60"/></w:pPr><w:rPr><w:color w:val="666666"/><w:i/><w:iCs/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/><w:basedOn w:val="Normal"/><w:pPr><w:ind w:left="360"/><w:spacing w:after="20" w:line="300" w:lineRule="auto"/><w:shd w:fill="F3F4F6"/></w:pPr><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas" w:eastAsia="Microsoft YaHei"/><w:sz w:val="19"/><w:szCs w:val="19"/></w:rPr></w:style>
  <w:style w:type="paragraph" w:styleId="TableText"><w:name w:val="Table Text"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="40"/><w:shd w:fill="F7F9FC"/></w:pPr><w:rPr><w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr></w:style>
</w:styles>
'@

$contentTypesXml = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>
  <Override PartName="/word/fontTable.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>
'@

$rootRelsXml = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>
'@

$documentRelsXml = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable" Target="fontTable.xml"/>
</Relationships>
'@

$settingsXml = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:settings xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:zoom w:percent="100"/>
  <w:characterSpacingControl w:val="doNotCompress"/>
  <w:themeFontLang w:val="zh-CN" w:eastAsia="zh-CN"/>
  <w:compat/>
</w:settings>
'@

$fontTableXml = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:fonts xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:font w:name="Microsoft YaHei"><w:family w:val="swiss"/><w:charset w:val="86"/></w:font>
  <w:font w:name="Consolas"><w:family w:val="modern"/><w:pitch w:val="fixed"/></w:font>
</w:fonts>
'@

$now = [DateTime]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
$coreXml = @"
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>$(Escape-Xml ([System.IO.Path]::GetFileNameWithoutExtension($markdownFullPath)))</dc:title>
  <dc:creator>YIAI Center</dc:creator>
  <cp:lastModifiedBy>YIAI Center</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">$now</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">$now</dcterms:modified>
</cp:coreProperties>
"@

$appXml = @'
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Microsoft Office Word</Application>
  <DocSecurity>0</DocSecurity>
  <ScaleCrop>false</ScaleCrop>
  <Company>YIAI Center</Company>
  <AppVersion>16.0000</AppVersion>
</Properties>
'@

$fileStream = [System.IO.File]::Open($temporaryPath, [System.IO.FileMode]::CreateNew, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
try {
    $archive = [System.IO.Compression.ZipArchive]::new($fileStream, [System.IO.Compression.ZipArchiveMode]::Create, $false)
    try {
        Add-ZipTextEntry -Archive $archive -EntryName '[Content_Types].xml' -Content $contentTypesXml
        Add-ZipTextEntry -Archive $archive -EntryName '_rels/.rels' -Content $rootRelsXml
        Add-ZipTextEntry -Archive $archive -EntryName 'word/document.xml' -Content $documentXml
        Add-ZipTextEntry -Archive $archive -EntryName 'word/styles.xml' -Content $stylesXml
        Add-ZipTextEntry -Archive $archive -EntryName 'word/settings.xml' -Content $settingsXml
        Add-ZipTextEntry -Archive $archive -EntryName 'word/fontTable.xml' -Content $fontTableXml
        Add-ZipTextEntry -Archive $archive -EntryName 'word/_rels/document.xml.rels' -Content $documentRelsXml
        Add-ZipTextEntry -Archive $archive -EntryName 'docProps/core.xml' -Content $coreXml
        Add-ZipTextEntry -Archive $archive -EntryName 'docProps/app.xml' -Content $appXml
    }
    finally {
        $archive.Dispose()
    }
}
finally {
    $fileStream.Dispose()
}

if ([System.IO.File]::Exists($outputFullPath)) {
    [System.IO.File]::Delete($outputFullPath)
}
[System.IO.File]::Move($temporaryPath, $outputFullPath)

Write-Output $outputFullPath
