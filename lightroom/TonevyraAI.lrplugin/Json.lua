local Json = {}

local Parser = {}
Parser.__index = Parser

local function escapeString(value)
  value = tostring(value)
  value = value:gsub("\\", "\\\\")
  value = value:gsub('"', '\\"')
  value = value:gsub("\n", "\\n")
  value = value:gsub("\r", "\\r")
  value = value:gsub("\t", "\\t")
  return '"' .. value .. '"'
end

local function isArray(value)
  if type(value) ~= "table" then
    return false
  end
  local count = 0
  for key, _ in pairs(value) do
    if type(key) ~= "number" then
      return false
    end
    if key > count then
      count = key
    end
  end
  return count > 0
end

function Json.encode(value)
  local kind = type(value)
  if kind == "nil" then
    return "null"
  end
  if kind == "boolean" then
    return value and "true" or "false"
  end
  if kind == "number" then
    return tostring(value)
  end
  if kind == "string" then
    return escapeString(value)
  end
  if kind == "table" then
    local parts = {}
    if isArray(value) then
      for index = 1, #value do
        table.insert(parts, Json.encode(value[index]))
      end
      return "[" .. table.concat(parts, ",") .. "]"
    end
    for key, item in pairs(value) do
      table.insert(parts, escapeString(key) .. ":" .. Json.encode(item))
    end
    return "{" .. table.concat(parts, ",") .. "}"
  end
  return escapeString(value)
end

function Parser:new(text)
  return setmetatable({ text = text, pos = 1, len = string.len(text) }, self)
end

function Parser:peek()
  return self.text:sub(self.pos, self.pos)
end

function Parser:next()
  local char = self:peek()
  self.pos = self.pos + 1
  return char
end

function Parser:skipSpace()
  while self.pos <= self.len do
    local char = self:peek()
    if char ~= " " and char ~= "\n" and char ~= "\r" and char ~= "\t" then
      break
    end
    self.pos = self.pos + 1
  end
end

function Parser:parseString()
  self:next()
  local parts = {}
  while self.pos <= self.len do
    local char = self:next()
    if char == '"' then
      return table.concat(parts)
    end
    if char == "\\" then
      local escaped = self:next()
      if escaped == "n" then
        table.insert(parts, "\n")
      elseif escaped == "r" then
        table.insert(parts, "\r")
      elseif escaped == "t" then
        table.insert(parts, "\t")
      else
        table.insert(parts, escaped)
      end
    else
      table.insert(parts, char)
    end
  end
  error("unterminated string")
end

function Parser:parseNumber()
  local start = self.pos
  while self.pos <= self.len do
    local char = self:peek()
    if not char:match("[0-9%+%-%.eE]") then
      break
    end
    self.pos = self.pos + 1
  end
  return tonumber(self.text:sub(start, self.pos - 1))
end

function Parser:parseLiteral(word, value)
  if self.text:sub(self.pos, self.pos + #word - 1) ~= word then
    error("invalid literal")
  end
  self.pos = self.pos + #word
  return value
end

function Parser:parseArray()
  self:next()
  local result = {}
  self:skipSpace()
  if self:peek() == "]" then
    self:next()
    return result
  end
  while true do
    table.insert(result, self:parseValue())
    self:skipSpace()
    local char = self:next()
    if char == "]" then
      return result
    end
    if char ~= "," then
      error("expected array comma")
    end
  end
end

function Parser:parseObject()
  self:next()
  local result = {}
  self:skipSpace()
  if self:peek() == "}" then
    self:next()
    return result
  end
  while true do
    self:skipSpace()
    local key = self:parseString()
    self:skipSpace()
    if self:next() ~= ":" then
      error("expected object colon")
    end
    result[key] = self:parseValue()
    self:skipSpace()
    local char = self:next()
    if char == "}" then
      return result
    end
    if char ~= "," then
      error("expected object comma")
    end
  end
end

function Parser:parseValue()
  self:skipSpace()
  local char = self:peek()
  if char == '"' then
    return self:parseString()
  end
  if char == "{" then
    return self:parseObject()
  end
  if char == "[" then
    return self:parseArray()
  end
  if char == "t" then
    return self:parseLiteral("true", true)
  end
  if char == "f" then
    return self:parseLiteral("false", false)
  end
  if char == "n" then
    return self:parseLiteral("null", nil)
  end
  return self:parseNumber()
end

function Json.decode(text)
  local parser = Parser:new(text)
  return parser:parseValue()
end

return Json
