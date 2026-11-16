def add(a):
    a+=1
    yield a

a=1
for i in add(a):
    next(i)
    
print(a)