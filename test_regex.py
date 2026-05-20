import re

# Test string
s = '----------------[1]----------------[0.868702839083807,0.23646357785781572,1]'

# Full pattern (without trailing dashes - there's no dash at the end!)
p_full = re.compile(r'^-+\[(\d+)\]-+\[([\d.]+),([\d.]+),(\d+)\]$')

print(f'Test string: {repr(s)}')
print(f'p_full (no trailing dashes): {p_full.pattern}')
print(f'p_full match: {p_full.match(s)}')

# Verify the pattern matches correctly
m = p_full.match(s)
if m:
    print(f'  groups: {m.groups()}')