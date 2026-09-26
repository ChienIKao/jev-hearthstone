"""Count-dependent positions; measured overrides take precedence over estimates."""
def _checked(points, count):
    if len(points)!=count or any(len(p)!=2 or not all(0.01<=v<=0.99 for v in p) for p in points):
        raise ValueError('校準點數或範圍不正確')
    if any(a[0]>=b[0] for a,b in zip(points,points[1:])):
        raise ValueError('校準點必須從左到右排列')
    return [list(p) for p in points]


def hand_points(count, layout):
    if not 0<=count<=10:
        raise ValueError('目前定位支援 0～10 張手牌')
    if not count:
        return [], 'empty'
    saved=layout.get('hand_overrides',{})
    if str(count) in saved:
        return _checked(saved[str(count)],count), 'calibrated'
    anchors=[]
    for key,points in saved.items():
        n=int(key)
        if 2<=n<=10:
            points=_checked(points,n)
            center=(points[0][0]+points[-1][0])/2
            span=points[-1][0]-points[0][0]
            low=min(p[1] for p in points)
            curve=(points[0][1]+points[-1][1])/2-low
            anchors.append((n,center,span,low,curve))
    anchors.sort()
    if anchors:
        a=min(anchors,key=lambda row:abs(row[0]-count))
        center,span,low,curve=a[1:]
        span=min(0.36,span*(count-1)/(a[0]-1))
        for a,b in zip(anchors,anchors[1:]):
            if a[0]<count<b[0]:
                t=(count-a[0])/(b[0]-a[0])
                center,span,low,curve=[x+(y-x)*t for x,y in zip(a[1:],b[1:])]
                break
    else:
        center=layout['hand_center']
        span=min(layout['hand_max_span'],(count-1)*layout['hand_step'])
        low,curve=0.915,0.035
    points=[]
    for i in range(count):
        t=2*i/(count-1)-1 if count>1 else 0
        points.append([center+t*span/2,low+curve*t*t])
    return _checked(points,count),'estimated'


def board_points(count,side,layout):
    if not 0<=count<=7 or side not in ('me','enemy'):
        raise ValueError('目前定位支援雙方各 0～7 個場上位置')
    saved=layout.get('board_overrides',{}).get(f'{side}:{count}')
    if saved is not None:
        return _checked(saved,count)
    return _checked([[layout['board_center']+(i-(count-1)/2)*layout['board_step'],
                      layout['board_'+side+'_y']] for i in range(count)],count)
