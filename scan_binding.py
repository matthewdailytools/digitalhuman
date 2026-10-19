"""Neutral-scan anatomical weights in centimetres; pure math shared with verification."""
import heapq
import math


def smooth(lo,hi,value):
    t=max(0.0,min(1.0,(value-lo)/(hi-lo)))
    return t*t*(3-2*t)


def distances(points,faces,seed):
    adjacent=[set() for _ in points]
    for face in faces:
        for a,b in zip(face,face[1:]+face[:1]):
            adjacent[a].add(b);adjacent[b].add(a)
    result=[math.inf]*len(points);result[seed]=0.0;pending=[(0.0,seed)]
    while pending:
        distance,index=heapq.heappop(pending)
        if result[index]!=distance:continue
        for neighbor in adjacent[index]:
            candidate=distance+math.dist(points[index],points[neighbor])
            if candidate<result[neighbor]:
                result[neighbor]=candidate;heapq.heappush(pending,(candidate,neighbor))
    return result


def jaw_weights(points,faces,upper,lower):
    du,dl=distances(points,faces,upper),distances(points,faces,lower)
    weights=[]
    for i,(x,y,z) in enumerate(points):
        w=smooth(16,19.4,z)*(1-smooth(23.2,26,z))*(1-smooth(-6,-2,y))
        if abs(x)<3.8 and 21.8<z<25.4 and y<-10.7:
            split=smooth(-.7,.7,du[i]-dl[i])
            blend=(1-smooth(2.5,3.8,abs(x)))*smooth(-10.7,-12,y)
            w=w*(1-blend)+split*blend
        w*=1-smooth(5,8.5,abs(x))
        weights.append(max(0,min(1,w)))
    return weights


def blink_delta(point,centers):
    x,y,z=point
    for cx,cy,cz in centers:
        dx=x-cx
        if abs(dx)>1.8 or not cz-1.2<z<cz+1.45 or y>-10.5:continue
        aperture=math.sqrt(max(0,1-(dx/1.60)**2))
        side=1-smooth(1.45,1.8,abs(dx))
        front=1-smooth(-11.4,-10.5,y)
        upper=cz+.50*aperture+.025*dx
        lower=cz-.43*aperture+.025*dx
        seam=cz-.18*aperture+.025*dx
        if z>=cz:
            weight=1-smooth(.12,1.15,max(0,z-upper))
            dz=(seam-upper)*weight
        else:
            weight=1-smooth(.12,.85,max(0,lower-z))
            dz=(seam-lower)*weight
        return (0,0,dz*side*front)
    return (0,0,0)


def smile_delta(point):
    x,y,z=point
    if y>-7 or not 20<z<29:return (0,0,0)
    corner=math.exp(-((abs(x)-2.25)/1.5)**2-((z-23.8)/1.75)**2)
    cheek=math.exp(-((abs(x)-4.1)/1.7)**2-((z-26.1)/1.55)**2)
    front=1-smooth(-11,-7,y)
    return ((1 if x>0 else -1)*(.34*corner+.10*cheek)*front,
            -.08*corner*front,(.55*corner+.25*cheek)*front)


def hairline(x,y):
    front=smooth(-1,-9,y)
    return 28.0+7.0*front+.012*x*x*front+.10*math.sin(3.1*x+.7*y)+.06*math.sin(6.2*x)
