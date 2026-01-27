def get_coords_for_rectangle(bottom_left:tuple, top_right:tuple):
    """
    Generates rectangle coordinates for geoJSON from lcm coordinates
    """
    rectangle = [[bottom_left[0], bottom_left[1]],
             [bottom_left[0], top_right[1]],
             [top_right[0], top_right[1]],
             [top_right[0], bottom_left[1]],
             [bottom_left[0], bottom_left[1]]]
    return rectangle

def grid_from_rectangle(bottom_left:tuple, top_right:tuple, w=500, h=500, outline=None, gap_between_squares=100):
    """ 
    Generates rectangle grid for geoJSON from lcm coordinates
    w: width
    h: height
    outline: another polygon (region of interest) to be used as a mask to discard rectangles that are not of interest
    gap_between_squares: space to leave between squares of the grid (to allow for laser capture with the RoboLPC function)
    """
    from shapely.geometry import Point
    from shapely.geometry.polygon import Polygon
    import math
    
    num_sqx = math.ceil((top_right[0] - bottom_left[0])/w)
    num_sqy = math.ceil((top_right[1] - bottom_left[1])/h)
    small_square_x = w
    small_square_y = h
    x_vals = [(bottom_left[0] + small_square_x*i) for i in range(num_sqx+1)]
    y_vals = [(bottom_left[1] + small_square_y*i) for i in range(num_sqy+1)]
    coord_list = []
    for num_x, each_x in enumerate(x_vals):
        for num_y, each_y in enumerate(y_vals):
            if num_x < num_sqx and num_y < num_sqy:
                coord_list.append([[each_x + gap_between_squares, each_y + gap_between_squares], [x_vals[num_x+1], y_vals[num_y+1]]])
    grid = [get_coords_for_rectangle(each[0] , each[1]) for each in coord_list]
    print(grid)
    for i, each_rect in enumerate(grid):
        if outline is not None:
            polygon = Polygon(outline)
            points = [(p[0], p[1]) for p in each_rect]
            print(points)
            isinoutline = sum([polygon.contains(Point(x)) for x in points])
            if isinoutline < 2:
                grid[i] = None
            
    return [rect for rect in grid if rect is not None]
    
def json_chunk(points_list, isgrid=True, name="object", w=500, h=500, gap_between_squares=100, outline=None, includebigsquares=False, numcornerstoinclude=1):
    """ 
    Generates json chunk from a list of points
    points_list: list of points; if length == 1: a dot, if length == 2: a rectangle, if length > 2: a freehand polygon
    isgrid: if true, generate a grid for rectangles
    name: name of the object
    w: width of grid square - passed to grid_from_rectangle()
    h: height of grid square - passed to grid_from_rectangle()
    outline: polygon region of interest (see grid_from_rectangle())
    includebigsquares: if true, output the square itself in addition to a grid generated from the square
    """
    from shapely.geometry import Point
    from shapely.geometry.polygon import Polygon
    print(len(points_list))
    all_chunks = []
    if len(points_list) < 1:
        return None
    elif len(points_list) == 1:
        chunk = f"""
                {{
                  "type": "Feature",
                  "geometry": {{
                    "type": "Point",
                    "coordinates": [{points_list[0][0]},{points_list[0][1]}]
                  }},
                  "properties": {{
                    "object_type": "annotation",
                    "isLocked": false
                  }}
                }}
        """
        return chunk
    elif len(points_list) == 2:

        grid = []
        bottom_left = points_list[0]
        top_right = points_list[1]

        if isgrid:
            grid = grid_from_rectangle(bottom_left, top_right, w=w, h=h, gap_between_squares=gap_between_squares)
            counter = 1
            for each in grid:
                chunk = ""
                if outline is not None:
                    polygon = Polygon(outline)
                    points = [(p[0], p[1]) for p in each]
                    isinoutline = sum([polygon.contains(Point(x)) for x in points])
                    print(isinoutline, points)
                else:
                    isinoutline = numcornerstoinclude + 1 # keep square if no outline polygon is given

                if isinoutline > numcornerstoinclude:
                    coords = ",\n".join(["[" + str(p[0]) + "," + str(p[1]) + "]" for p in each])
                    subgrid_name = f"{name}_sg{counter:05}"
                    chunk = f"""
                            {{
                              "type": "Feature",
                              "geometry": {{
                                "type": "Polygon",
                                "coordinates": [
                                  [
                                    {coords}
                                  ]
                                ]
                              }},
                              "properties": {{
                                "object_type": "annotation",
                                "name": "{subgrid_name}",
                                "isLocked": false
                              }}
                            }}
                    """
                counter += 1
                if chunk != "":
                    all_chunks.append(chunk)
            all_chunks = ",\n".join(all_chunks)

        else:
            all_chunks = ""

        if includebigsquares:
            rectangle = []
            bottom_left = points_list[0]
            top_right = points_list[1]
            rectangle = get_coords_for_rectangle(bottom_left, top_right)
            coords = ",\n".join(["[" + str(p[0]) + "," + str(p[1]) + "]" for p in rectangle])
            chunk = f"""
                    {{
                      "type": "Feature",
                      "geometry": {{
                        "type": "Polygon",
                        "coordinates": [
                          [
                            {coords}
                          ]
                        ]
                      }},
                      "properties": {{
                        "object_type": "annotation",
                        "name": "{name}",
                        "isLocked": false
                      }}
                    }}
            """
        else:
            chunk = ""
    else: #len(points_list) > 2:
        polygon = []
        polygon = points_list + [points_list[0]] # make closed polygon
        coords = ",\n".join(["[" + str(p[0]) + "," + str(p[1]) + "]" for p in polygon])
        chunk = f"""
                {{
                  "type": "Feature",
                  "geometry": {{
                    "type": "Polygon",
                    "coordinates": [
                      [
                        {coords}
                      ]
                    ]
                  }},
                  "properties": {{
                    "object_type": "annotation",
                    "name": "{name}",
                    "isLocked": false
                  }}
                }}
        """
        all_chunks = ""
    if all_chunks == "":
        return chunk
    elif chunk != "":
        return all_chunks + "," + chunk
    else:
        return all_chunks
        


def aida_to_qupath(points_list, rotate=False, horizontal_flip=False, multiply_by=1, transform=(0, 0)):
    if rotate:
        coords = [[p[1], p[0]] for p in points_list]

    if horizontal_flip:
        coords = [[100000-p[0], p[1]] for p in coords]

    coords.append(coords[0])
    coords = [[p[0]*multiply_by, p[1]*multiply_by] for p in coords]
    coords = [[p[0] + transform[0], p[1] + transform[1]] for p in coords]
    chunk = f"""
        {{
          "type": "Feature",
          "geometry": {{
            "type": "Polygon",
            "coordinates": [
              
                {coords}
              
            ]
          }},
          "properties": {{
            "object_type": "annotation",
            "isLocked": false
          }}
        }}
    """
    return chunk

def palm2qupath_affine(filename=None, warp_matrix=None):
    """ 
    Generates geoJSON from palm elements exported text
    warp_matrix: obtained from cv2.getAffineTransform(src, dest)
    Updated on 2024/02/08
    """

    import io
    import pandas
    import cv2
    import numpy

    with open(filename) as elements_file:
        lines = elements_file.readlines()

    new_lines = ['']
    for each in lines:
        if not (each.startswith("Dot") or each.startswith("Rectangle") or each.startswith("Type")  or each.startswith("Freehand")  or each.startswith("Line")):
            coords = each.replace("\t", ":")
            coords = ''.join(coords).replace("\t", "")
            new_line = new_lines[-1].replace("\n", "") + "" + coords
            new_lines[-1] =  new_line.replace("\n", ":")
        else:
            new_lines.append(each)

    new_lines = "\n".join([line.replace(".:", "") for line in new_lines])
    # print(new_lines)

    buffer = io.StringIO(new_lines)

    elements = pandas.read_csv(buffer, sep="\t", skiprows=1, on_bad_lines='skip')
    print(elements.head())
    elements['Coordinates'] = elements.apply(lambda x: x['Coordinates'].split(":"), axis=1)
    elements['Coordinates'] = elements.Coordinates.apply(lambda x: [[float(pair.split(",")[0]), float(pair.split(",")[1])] for pair in x if pair != ""])
    # [[float(pair.split(",")[0]), float(pair.split(",")[1])] for pair in elements['Coordinates'][0] if pair != ""]


    elements['Coordinates_qupath'] = elements.Coordinates.apply(lambda x: cv2.transform(numpy.float32(x)[None, :, :], warp_mat)[0].tolist())
    json_text = "[\n" + elements.apply(lambda x: qupath2palm.json_chunk(x['Coordinates_qupath'], name=x['Well'], isgrid=False, includebigsquares=True), axis=1).str.cat(sep=",\n") + "\n]"

#     json_text = "[\n" + elements.apply(lambda x: qupath2palm.json_chunk(x['Coordinates_qupath'], name=x['Well'], isgrid=False, includebigsquares=True)).str.cat(sep=",\n") + "\n]"
    return json_text
# def palm2qupath_affine(filename=None, warp_matrix=None):
#     """ 
#     Generates geoJSON from palm elements exported text
#     warp_matrix: obtained from cv2.getAffineTransform(src, dest)
#     """

#     import io
#     import pandas
#     import cv2
#     import numpy

#     with open(filename) as elements_file:
#         lines = elements_file.readlines()

#     new_lines = ['']
#     for each in lines:
#         if not (each.startswith("Dot") or each.startswith("Rectangle") or each.startswith("Type")  or each.startswith("Freehand")):
#             coords = each.replace("\t", ":")
#             coords = ''.join(coords).replace("\t", "")
#             new_line = new_lines[-1].replace("\n", "") + "" + coords
#             new_lines[-1] =  new_line.replace("\n", ":")
#         else:
#             new_lines.append(each)

#     new_lines = "\n".join([line.replace(".:", "") for line in new_lines])
#     # print(new_lines)

#     buffer = io.StringIO(new_lines)

#     elements = pandas.read_csv(buffer, sep="\t", skiprows=1, on_bad_lines='skip')
#     elements['Coordinates'] = elements.apply(lambda x: x['Coordinates'].split(":"), axis=1)
#     elements['Coordinates'] = elements.Coordinates.apply(lambda x: [[float(pair.split(",")[0]), float(pair.split(",")[1])] for pair in x if pair != ""])
#     # [[float(pair.split(",")[0]), float(pair.split(",")[1])] for pair in elements['Coordinates'][0] if pair != ""]


#     elements['Coordinates_qupath'] = elements.Coordinates.apply(lambda x: cv2.transform(numpy.float32(x)[None, :, :], warp_mat)[0].tolist())
#     json_text = "[\n" + elements['Coordinates_qupath'].apply(lambda x: qupath2palm.json_chunk(x, isgrid=False, includebigsquares=True)).str.cat(sep=",\n") + "\n]"

#     json_text = "[\n" + elements['Coordinates_qupath'].apply(lambda x: json_chunk(x, isgrid=False, includebigsquares=True)).str.cat(sep=",\n") + "\n]"
#     return json_text

def qupath2qupath_affine(filename, warp_mat, isgrid=False, w=4000, h=4000, gap_between_squares=50, numcornerstoinclude=1, min_size_mm=0.3, randomise=False):
    """ 
    Generates palm elements text file from geoJSON
    warp_mat calculated from reference points
    """
    # TODO
    # If max dimension of an outline polygon is less than min_size_mm, leave the polygon as is
    import json
    import cv2
    import numpy
    import qupath2palm

    if warp_mat == "identity":
        warp_mat = numpy.array([[ 1., -0.,  0.],[ 0.,  1.,  0.]])

    with open(filename) as json_file: #QuPath/rectangles_nocollection.geojson
        qupath = json.load(json_file)

    all_json = []
    object_num = 0
    for each in qupath:
        polygon = each['geometry']['coordinates']
        geom_type = each['geometry']['type']
        
        if geom_type == "MultiPolygon": # skip this geometry for now
            continue
        # print(polygon)
        try:
            comment = each['properties']['name']
        except KeyError:
            comment = ""
        if isinstance(polygon[0], list): # this is the case if coordinates field has more than one point
            polygon = polygon[0]
            polygon = cv2.transform(numpy.float32(polygon)[None, :, :], warp_mat)[0]
        elif isinstance(polygon[0], float) or isinstance(polygon[0], int):
            polygon = cv2.transform(numpy.float32([polygon])[None, :, :], warp_mat)[0]
        print(len(polygon))
        if len(polygon) == 5:
            polygon = [polygon[i] for i in [0, 1, 2, 3]]
        else:
            polygon = [polygon[i] for i in range(len(polygon))]
        if isgrid:
            outline = polygon
            polygon = list(cv2.boundingRect(numpy.float32(polygon)))
            polygon = [(polygon[0], polygon[1]), (polygon[0] + polygon[2], polygon[1] + polygon[3])]
        json_text = qupath2palm.json_chunk(polygon, name=comment+f"_{object_num:05}", 
                                           isgrid=isgrid, includebigsquares=False, outline=outline, 
                                           w=w, h=h, gap_between_squares=gap_between_squares, numcornerstoinclude=numcornerstoinclude) 
        all_json.append(json_text)
        object_num += 1
    if randomise:
        print("randomising tiles!!!!")
        import random
        random.shuffle(all_json)
    all_json = ",\n".join(all_json)
    return "[\n" + all_json + "\n]"


# def qupath2qupath_affine(filename, warp_mat):
#     """ 
#     Generates palm elements text file from geoJSON
#     warp_mat calculated from reference points
#     """

#     import json
#     import cv2
#     import numpy
#     import qupath2palm
    
#     with open(filename) as json_file: #QuPath/rectangles_nocollection.geojson
#         qupath = json.load(json_file)

#     all_json = []
#     for each in qupath:
#         polygon = each['geometry']['coordinates']
#         geom_type = each['geometry']['type']
        
#         if geom_type == "MultiPolygon": # skip this geometry for now
#             continue
#         # print(polygon)
#         try:
#             comment = each['properties']['name']
#         except KeyError:
#             comment = ""
#         if isinstance(polygon[0], list): # this is the case if coordinates field has more than one point
#             polygon = polygon[0]
#             polygon = cv2.transform(numpy.float32(polygon)[None, :, :], warp_mat)[0]
#         elif isinstance(polygon[0], float) or isinstance(polygon[0], int):
#             polygon = cv2.transform(numpy.float32([polygon])[None, :, :], warp_mat)[0]
#         print(len(polygon))
#         if len(polygon) == 5:
#             polygon = [polygon[i] for i in [0, 1, 2, 3]]
#         else:
#             polygon = [polygon[i] for i in range(len(polygon))]
#         # horizontal flip
#         # polygon = [[image_width - p[0], p[1]] for p in polygon]
#         json_text = qupath2palm.json_chunk(polygon, isgrid=False, includebigsquares=True) 
#         all_json.append(json_text)
#     all_json = ",\n".join(all_json)
#     return "[\n" + all_json + "\n]"

def qupath2palm_affine(filename, warp_mat, print_to_screen=True):
    """
    Generates palm elements text file from geoJSON
    warp_mat: affine matrix from 2 points along the slide (cover the entire slide as much as possible)
    """

    import json
    import cv2
    import numpy
   
    with open(filename) as json_file: #QuPath/rectangles_nocollection.geojson
        qupath = json.load(json_file)
   
    colour = "red"
    thickness = 2
    counter = 1
    cutshot = "0,0"
    from datetime import datetime
    datetime_str = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
    datetime_str = datetime_str.split()

    z = 6397
    elements_text = []
    if not isinstance(qupath, list):
#         qupath = [qupath, qupath]
       
        polygon = qupath['geometry']['coordinates'][0]
        try:
            comment = each['properties']['name']
        except:
            comment = ""
#         polygon = [polygon[p] for p in [0,2]]
        polygon = cv2.transform(numpy.float32(polygon)[None, :, :], warp_mat)[0].tolist()
        # horizontal flip
        # polygon = [[image_width - p[0], p[1]] for p in polygon]
        area = abs((polygon[2][0]-polygon[0][0])*(polygon[2][1]-polygon[0][1]))
        if len(polygon) == 5:
            element_line = f"Rectangle\t{colour}\t{thickness}\t{counter}\t{cutshot}\t{area}\t{z}\t{comment}\n.\t{polygon[0][0]},{polygon[0][1]}\t{polygon[2][0]},{polygon[2][1]}"
#             print(element_line)
            elements_text.append(element_line)
    else:
        for each in qupath:
            polygon = each['geometry']['coordinates'][0]
            try:
                comment = each['properties']['name']
            except:
                comment = ""
            polygon = cv2.transform(numpy.float32(polygon)[None, :, :], warp_mat)[0].tolist()
            print(polygon)
            area = abs((polygon[2][0]-polygon[0][0])*(polygon[2][1]-polygon[0][1]))
            if len(polygon) == 5: # if
                element_line = f"Rectangle\t{colour}\t{thickness}\t{counter}\t{cutshot}\t{area}\t{z}\t{comment}\n.\t{polygon[0][0]},{polygon[0][1]}\t{polygon[2][0]},{polygon[2][1]}"
                elements_text.append(element_line)
            else:
                polygon_text = [','.join([str(x), str(y)]) for x,y in polygon]
                polygon_text = [polygon_text[i:i+5] for i in range(0, len(polygon_text), 5)]
                polygon_text = "\n".join([".\t" + "\t".join(each_line) for each_line in polygon_text])
                element_line = f"Freehand\t{colour}\t{thickness}\t{counter}\t{cutshot}\t0\t{z}\t{comment}\n{polygon_text}"
                elements_text.append(element_line)
            counter += 1    
    elements_text = "\n\n".join(elements_text)

    elements_text = f"""PALMRobo Elements\nVersion: V 4.8.0.1\nDate, Time : {datetime_str[0]}  {datetime_str[1]}\nMICROMETER\nElements :\nType  Color   Thickness   No  CutShot Area    Z   Comment Coordinates\n\n{elements_text}
    """
    if print_to_screen:
        print(elements_text)
    return elements_text

def qupath2palm_affine_new(filename, warp_mat, print_to_screen=True):
    """
    Generates palm elements text file from geoJSON
    warp_mat: affine matrix from 2 points along the slide (cover the entire slide as much as possible)
    Supports both FeatureCollection and list-of-features formats.
    """

    import json
    import cv2
    import numpy

    with open(filename) as json_file: #QuPath/rectangles_nocollection.geojson
        qupath = json.load(json_file)

    # Handle FeatureCollection format
    if isinstance(qupath, dict) and qupath.get('type') == 'FeatureCollection':
        qupath = qupath.get('features', [])

    colour = "red"
    thickness = 2
    counter = 1
    cutshot = "0,0"
    laser_function = "RoboLPC"
    well = ""
    objective = ""
    
    from datetime import datetime
    datetime_str = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
    datetime_str = datetime_str.split()

    z = 6397
    elements_text = []
    if not isinstance(qupath, list):
#         qupath = [qupath, qupath]
       
        polygon = qupath['geometry']['coordinates'][0]
        try:
            comment = each['properties']['name']
        except:
            comment = ""
#         polygon = [polygon[p] for p in [0,2]]
        polygon = cv2.transform(numpy.float32(polygon)[None, :, :], warp_mat)[0].tolist()
        # horizontal flip
        # polygon = [[image_width - p[0], p[1]] for p in polygon]
        area = abs((polygon[2][0]-polygon[0][0])*(polygon[2][1]-polygon[0][1]))
    
        if len(polygon) == 5:
                element_line = f"Rectangle\t{colour}\t{thickness}\t{counter}\t{laser_function}\t{cutshot}\t{area}\t{z}\t{well}\t{objective}\t{comment}\n.\t{polygon[0][0]},{polygon[0][1]}\t{polygon[2][0]},{polygon[2][1]}"
    #             print(element_line)
                elements_text.append(element_line)
    
    else:
        for each in qupath:
            polygon = each['geometry']['coordinates'][0]
            try:
                comment = each['properties']['name']
            except:
                comment = ""
            polygon = cv2.transform(numpy.float32(polygon)[None, :, :], warp_mat)[0].tolist()
            print(polygon)
            area = abs((polygon[2][0]-polygon[0][0])*(polygon[2][1]-polygon[0][1]))
            if len(polygon) == 5: # if
                element_line = f"Rectangle\t{colour}\t{thickness}\t{counter}\t{laser_function}\t{cutshot}\t{area}\t{z}\t{well}\t{objective}\t{comment}\n.\t{polygon[0][0]},{polygon[0][1]}\t{polygon[2][0]},{polygon[2][1]}"
                elements_text.append(element_line)
            else:
                polygon_text = [','.join([str(x), str(y)]) for x,y in polygon]
                polygon_text = [polygon_text[i:i+5] for i in range(0, len(polygon_text), 5)]
                polygon_text = "\n".join([".\t" + "\t".join(each_line) for each_line in polygon_text])
                element_line = f"Freehand\t{colour}\t{thickness}\t{counter}\t{cutshot}\t0\t{z}\t{comment}\n{polygon_text}"
                elements_text.append(element_line)
            counter += 1    
    elements_text = "\n\n".join(elements_text)

    elements_text = f"""PALMRobo Elements\nVersion: V 4.8.0.1\nDate, Time : 13.10.2022  12:14:59\nMICROMETER\nElements :\nType\tColor\tThickness\tNo\tLaser function\tCutShot\tArea\tZ\tWell\tObjective\tComment\tCoordinates\n\n{elements_text}
    """
    if print_to_screen:
        print(elements_text)
    return elements_text



def get_affinemat_from_images(img1_path, img2_path):
    """_summary_ - don't use, this isn't as good as manually selecting 3 points

    Args:
        img1_path (str): path and name of the first image
        img2_path (str): path and name of the second image
    """
    import cv2
    import numpy as np

    img1 = cv2.imread(img1_path)
    img2 = cv2.imread(img2_path)

    # Convert both images to LAB color space
    # lab1 = landscape # cv2.cvtColor(landscape, cv2.COLOR_BGR2LAB)
    # lab2 = portrait # cv2.cvtColor(portrait, cv2.COLOR_BGR2LAB)
    
    # -------- normalise colours ----------
    # Calculate the mean and standard deviation of each channel in both images
    mean_img2, std_img2 = cv2.meanStdDev(img2)
    mean_img1, std_img1 = cv2.meanStdDev(img1)

    # Adjust the first image's LAB channels to match the mean and standard deviation of the second image
    img2[:, :, 0] = (img2[:, :, 0] - mean_img2[0]) * (std_img1[0] / std_img2[0]) + mean_img1[0]
    img2[:, :, 1] = (img2[:, :, 1] - mean_img2[1]) * (std_img1[1] / std_img2[1]) + mean_img1[1]
    img2[:, :, 2] = (img2[:, :, 2] - mean_img2[2]) * (std_img1[2] / std_img2[2]) + mean_img1[2]

    # Convert the adjusted LAB image back to BGR color space
    # color_corrected_img2 = landscape # cv2.cvtColor(lab1, cv2.COLOR_LAB2BGR)


    stacked = np.hstack([cv2.resize(img1, img2.shape[:2][::-1]), img2])
    cv2.imshow('colour correction', stacked)

    gray_img1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray_img2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    # Initiate SIFT detector
    sift = cv2.SIFT_create()
    # find the keypoints and descriptors with SIFT
    kp1, des1 = sift.detectAndCompute(gray_img1,None)
    kp2, des2 = sift.detectAndCompute(gray_img2,None)
    # BFMatcher with default params
    bf = cv2.BFMatcher()
    matches = bf.knnMatch(des1,des2,k=2)

    # Apply ratio test
    good = []
    for m,n in matches:
        if m.distance < 0.70*n.distance:
            good.append([m])
            
    # good = [good[x] for x in [0, 7, 21]]
    match_img = cv2.drawMatchesKnn(gray_img1,kp1,gray_img2,kp2,good,None,flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
    #------
    imS = cv2.resize(match_img, (1920, 1080)) 
    cv2.imshow('Matches', imS)

    src_pts = np.float32([ kp1[m[0].queryIdx].pt for m in good ]).reshape(-1,1,2)
    dst_pts = np.float32([ kp2[m[0].trainIdx].pt for m in good]).reshape(-1,1,2)

    # using affine transformation
    (M, mask) = cv2.estimateAffine2D(src_pts, dst_pts, method=cv2.RANSAC)
    (h, w) = img2.shape[:2]
    aligned_img1 = cv2.warpAffine(img1, M, (w, h))
    print(M)

    stacked = np.hstack([aligned_img1, img2])
    cv2.imshow('stacked', stacked)
    overlay = img2.copy()
    output = aligned_img1.copy()
    cv2.addWeighted(overlay, 0.5, output, 0.5, 0, output)
    cv2.imshow('overlay', output)
    cv2.waitKey()
    cv2.destroyAllWindows()
    for i in range (1,5):
        cv2.waitKey(1)
    
    return M

def obtain_centres_from_geojson_polygons(filename):
    import json
    import cv2
    import numpy
    import qupath2palm

    with open(filename) as json_file: #QuPath/rectangles_nocollection.geojson
        qupath = json.load(json_file)

    centres = []
    for each in qupath:
        polygon = each['geometry']['coordinates']
        geom_type = each['geometry']['type']

        if geom_type == "MultiPolygon": # skip this geometry for now
            continue
        # print(polygon)
        try:
            comment = each['properties']['name']
        except KeyError:
            comment = ""
        if isinstance(polygon[0], list): # this is the case if coordinates field has more than one point
            polygon = polygon[0]

        polygon = numpy.array(polygon)
        # Extract x and y coordinates
        x_coordinates = polygon[:, 0]
        y_coordinates = polygon[:, 1]
        centroid = [numpy.mean(x_coordinates), numpy.mean(y_coordinates)]
        centres.append(centroid)

    return centres
    
# Get perspective transform matrix
def perspective_transform(points, perspective_matrix):
    import numpy
    # Convert points to homogeneous coordinates (add a column of ones)
    homogeneous_points = numpy.column_stack((points, numpy.ones(len(points))))

    # Apply perspective transformation
    transformed_points = numpy.dot(perspective_matrix, homogeneous_points.T).T

    # Convert back to Cartesian coordinates
    transformed_points_cartesian = transformed_points[:, :2] / transformed_points[:, 2, None]

    return transformed_points_cartesian


def qupath2qupath_perspective(filename, warp_mat):
    """ 
    Generates palm elements text file from geoJSON
    warp_mat calculated from reference points
    """

    import json
    import cv2
    import numpy
    import qupath2palm
    
    with open(filename) as json_file: #QuPath/rectangles_nocollection.geojson
        qupath = json.load(json_file)

    all_json = []
    for each in qupath:
        polygon = each['geometry']['coordinates']
        geom_type = each['geometry']['type']
        
        if geom_type == "MultiPolygon": # skip this geometry for now
            continue
        # print(polygon)
        try:
            comment = each['properties']['name']
        except KeyError:
            comment = ""
        if isinstance(polygon[0], list): # this is the case if coordinates field has more than one point
            polygon = polygon[0]
            polygon = perspective_transform(numpy.float32(polygon), warp_mat)
        elif isinstance(polygon[0], float) or isinstance(polygon[0], int):
            polygon = perspective_transform(numpy.float32([polygon]), warp_mat)
        print(len(polygon))
        if len(polygon) == 5:
            polygon = [polygon[i] for i in [0, 1, 2, 3]]
        else:
            polygon = [polygon[i] for i in range(len(polygon))]
        # horizontal flip
        # polygon = [[image_width - p[0], p[1]] for p in polygon]
        json_text = qupath2palm.json_chunk(polygon, name=comment, isgrid=False, includebigsquares=True) 
        all_json.append(json_text)
    all_json = ",\n".join(all_json)
    return "[\n" + all_json + "\n]"

def qupath2qupath_make_straight_rectangles(filename, isgrid=False, w=4000, h=4000, gap_between_squares=100, numcornerstoinclude=1):
    """ 
    Generates straight rectangle elements from geoJSON and outputs geoJSON
    A lot of the arguments are not actually used as the code for this function was copy-pasted from qupath2qupath_affine!
    """

    import json
    import cv2
    import numpy
    import qupath2palm

    scale = 1.0
    outline = None
    with open(filename) as json_file: #QuPath/rectangles_nocollection.geojson
        qupath = json.load(json_file)

    all_json = []
    for each in qupath:
        polygon = each['geometry']['coordinates']
        geom_type = each['geometry']['type']
        
        if geom_type == "MultiPolygon": # skip this geometry for now
            continue
        # print(polygon)
        try:
            comment = each['properties']['name']
        except KeyError:
            comment = ""
        if isinstance(polygon[0], list): # this is the case if coordinates field has more than one point
            polygon = polygon[0]
            print(polygon)
            polygon_array = numpy.float32(numpy.array(polygon))
            # Find the rotated rectangle
            rect = cv2.minAreaRect(polygon_array)

            # Extract rotation angle from the rotated rectangle
            angle_degrees = rect[2]
            print(angle_degrees)
            # Calculate the center of the rectangle
            center_x = numpy.mean(polygon_array[:, 0])
            center_y = numpy.mean(polygon_array[:, 1])
            center = rect[0]
            rotation_matrix = cv2.getRotationMatrix2D(center, angle_degrees, scale)
            print(rotation_matrix)
            polygon = cv2.transform(numpy.float32(polygon)[None, :, :], rotation_matrix)[0]
            rect_points = cv2.boxPoints(rect)
            polygon = cv2.transform(numpy.float32(rect_points)[None, :, :], rotation_matrix)[0]  # Convert to integer coordinates
        elif isinstance(polygon[0], float) or isinstance(polygon[0], int):
            polygon = numpy.float32([polygon])

            # Calculate the center of the rectangle
            center_x = numpy.mean(polygon[:, 0])
            center_y = numpy.mean(polygon[:, 1])
            center = (center_x, center_y)
            rotation_matrix = cv2.getRotationMatrix2D(center, angle_degrees, scale)
            polygon = cv2.transform(polygon[None, :, :], rotation_matrix)[0]
        print(len(polygon))
        if len(polygon) == 5:
            polygon = [polygon[i] for i in [0, 1, 2, 3]]
        else:
            polygon = [polygon[i] for i in range(len(polygon))]
        if isgrid:
            outline = polygon
            polygon = list(cv2.boundingRect(numpy.float32(polygon)))
            polygon = [(polygon[0], polygon[1]), (polygon[0] + polygon[2], polygon[1] + polygon[3])]
        json_text = qupath2palm.json_chunk(polygon, name=comment, 
                                           isgrid=isgrid, includebigsquares=False, outline=outline, 
                                           w=w, h=h, gap_between_squares=gap_between_squares, numcornerstoinclude=numcornerstoinclude) 
        all_json.append(json_text)
    all_json = ",\n".join(all_json)
    return "[\n" + all_json + "\n]"
    
# new function to handle irregular polygons

def qupath2palm_affine_irregular(filename, warp_mat, print_to_screen=True):
    """
    Generates palm elements text file from geoJSON
    warp_mat: affine matrix from 2 points along the slide (cover the entire slide as much as possible)
    Supports both FeatureCollection and list-of-features formats.
    """

    import json
    import cv2
    import numpy

    with open(filename) as json_file: #QuPath/rectangles_nocollection.geojson
        qupath = json.load(json_file)

    # Handle FeatureCollection format
    if isinstance(qupath, dict) and qupath.get('type') == 'FeatureCollection':
        qupath = qupath.get('features', [])

    colour = "red"
    thickness = 2
    counter = 1
    cutshot = "0,0"
    laser_function = "CenterRoboLPC"
    well = ""
    objective = ""

    z = 6397
    elements_text = []
    if not isinstance(qupath, list):
#         qupath = [qupath, qupath]
       
        polygon = qupath['geometry']['coordinates'][0]
        try:
            comment = each['properties']['name']
        except:
            comment = ""
#         polygon = [polygon[p] for p in [0,2]]
        polygon = cv2.transform(numpy.float32(polygon)[None, :, :], warp_mat)[0].tolist()
        # horizontal flip
        # polygon = [[image_width - p[0], p[1]] for p in polygon]
        area = abs((polygon[2][0]-polygon[0][0])*(polygon[2][1]-polygon[0][1]))
        if len(polygon) == 5:
            element_line = f"Rectangle\t{colour}\t{thickness}\t{counter}\t{laser_function}\t{cutshot}\t{area}\t{z}\t{well}\t{objective}\t{comment}\n.\t{polygon[0][0]},{polygon[0][1]}\t{polygon[2][0]},{polygon[2][1]}"
#             print(element_line)
            elements_text.append(element_line)
    else:
        for each in qupath:
            polygon = each['geometry']['coordinates'][0]
            try:
                comment = each['properties']['name']
            except:
                comment = ""
            polygon = cv2.transform(numpy.float32(polygon)[None, :, :], warp_mat)[0].tolist()
            print(polygon)
            area = abs((polygon[2][0]-polygon[0][0])*(polygon[2][1]-polygon[0][1]))
            if len(polygon) == 5: # if
                element_line = f"Line\t{colour}\t{thickness}\t{counter}\t{laser_function}\t{cutshot}\t{area}\t{z}\t{well}\t{objective}\t{comment}\n.\t{polygon[0][0]},{polygon[0][1]}\t{polygon[1][0]},{polygon[1][1]}\t{polygon[2][0]},{polygon[2][1]}\t{polygon[3][0]},{polygon[3][1]}\t{polygon[4][0]},{polygon[4][1]}"
                elements_text.append(element_line)
            else:
                polygon_text = [','.join([str(x), str(y)]) for x,y in polygon]
                polygon_text = [polygon_text[i:i+5] for i in range(0, len(polygon_text), 5)]
                polygon_text = "\n".join([".\t" + "\t".join(each_line) for each_line in polygon_text])
                element_line = f"Freehand\t{colour}\t{thickness}\t{counter}\t{laser_function}\t{cutshot}\t{area}\t{z}\t{well}\t{objective}\t{comment}\n.\t{polygon_text}"
                elements_text.append(element_line)
            counter += 1    
    elements_text = "\n\n".join(elements_text)

    elements_text = f"""PALMRobo Elements\nVersion: V 4.8.0.1\nDate, Time : 13.10.2022  12:14:59\nMICROMETER\nElements :\nType\tColor\tThickness\tNo\tLaser function\tCutShot\tArea\tZ\tWell\tObjective\tComment\tCoordinates\n\n{elements_text}
    """
    if print_to_screen:
        print(elements_text)
    return elements_text

if __name__ == "__main__":
   print("Nothing to do here yet, please use as an imported package for now!") 


def palm2qupath_affine_2(filename=None, warp_matrix=None):
    """ 
    Generates geoJSON from palm elements exported text
    warp_matrix: obtained from cv2.getAffineTransform(src, dest)
    """

    import io
    import pandas
    import cv2
    import numpy
    import qupath2palm

    with open(filename) as elements_file:
        lines = elements_file.readlines()

    new_lines = ['']
    for each in lines:
        if not (each.startswith("Dot") or each.startswith("Rectangle") or each.startswith("Type")  or each.startswith("Freehand")  or each.startswith("Line")):
            coords = each.replace("\t", ":")
            coords = ''.join(coords).replace("\t", "")
            new_line = new_lines[-1].replace("\n", "") + "" + coords
            new_lines[-1] =  new_line.replace("\n", ":")
        else:
            new_lines.append(each)

    new_lines = "\n".join([line.replace(".:", "") for line in new_lines])
    # print(new_lines)

    buffer = io.StringIO(new_lines)

    elements = pandas.read_csv(buffer, sep="\t", skiprows=1, on_bad_lines='skip')
    print(elements.head())
    elements['Coordinates'] = elements.apply(lambda x: x['Coordinates'].split(":"), axis=1)
    elements['Coordinates'] = elements.Coordinates.apply(lambda x: [[float(pair.split(",")[0]), float(pair.split(",")[1])] for pair in x if pair != ""])
    # [[float(pair.split(",")[0]), float(pair.split(",")[1])] for pair in elements['Coordinates'][0] if pair != ""]


    elements['Coordinates_qupath'] = elements.Coordinates.apply(lambda x: cv2.transform(numpy.float32(x)[None, :, :], warp_matrix)[0].tolist())
    json_text = "[\n" + elements.apply(lambda x: qupath2palm.json_chunk(x['Coordinates_qupath'], name=x['Well'], isgrid=False, includebigsquares=True), axis=1).str.cat(sep=",\n") + "\n]"

#     json_text = "[\n" + elements.apply(lambda x: qupath2palm.json_chunk(x['Coordinates_qupath'], name=x['Well'], isgrid=False, includebigsquares=True)).str.cat(sep=",\n") + "\n]"
    return json_text
# def palm2qupath(filename=None, multiplier_x=4.40, multiplier_y=None, 
#                 transform_x=127850.2975, transform_y=388333.7, vertical_flip=True, image_height=100000):
#     """ 
#     Generates geoJSON from palm elements exported text
#     multiplier_x, multiplier_y, transform_x, transform_y: get these calues from calculate_lm() ideally
#     vertical_flip: should the image be flipped vertically?
#     image_height: assume image height for vertical flipping
#     """

#     import io
#     import pandas
# #     import json

#     if multiplier_y is None:
#         multiplier_y = multiplier_x
#     with open(filename) as elements_file:
#         lines = elements_file.readlines()

#     new_lines = ['']
#     for each in lines:
#         if not (each.startswith("Dot") or each.startswith("Rectangle") or each.startswith("Type")  or each.startswith("Freehand")):
#             coords = each.replace("\t", ":")
#             coords = ''.join(coords).replace("\t", "")
#             new_line = new_lines[-1].replace("\n", "") + "" + coords
#             new_lines[-1] =  new_line.replace("\n", ":")
#         else:
#             new_lines.append(each)

#     new_lines = "\n".join([line.replace(".:", "") for line in new_lines])
#     print(new_lines)

#     buffer = io.StringIO(new_lines)

#     elements = pandas.read_csv(buffer, sep="\t", skiprows=1, on_bad_lines='skip')
#     elements['Coordinates'] = elements.apply(lambda x: x['Coordinates'].split(":"), axis=1)
#     elements['Coordinates'] = elements.Coordinates.apply(lambda x: [(float(y.split(",")[0]), float(y.split(",")[1])) for y in x if len(y.split(",")) > 1])

# #     multiplier_x = 4.40 # 4.3956
# #     multiplier_y = 4.40 # 4.419247
# #     intercept_x = 127850.2975 # 127651
# #     intercept_y = 388333.7 #390258
#     elements['Coordinates_qupath'] = elements.Coordinates.apply(lambda x: [(((p[0]*multiplier_x)+transform_x), ((p[1]*multiplier_y)+transform_y)) for p in x])
    
#     if vertical_flip:
#         elements['Coordinates_qupath'] = elements.Coordinates_qupath.apply(lambda x: [(p[0], image_height - p[1]) for p in x])
#         elements.head()
        
#     json_text = "[\n" + elements['Coordinates_qupath'].apply(lambda x: json_chunk(x, isgrid=False, includebigsquares=True)).str.cat(sep=",\n") + "\n]"
#     return json_text

# def calculate_lm(filename, direction="lcm2motic"):
#     """
#     Calculate linear model and output x and y multipliers and x and y transforms
#     file is in csv format with at least 4 columns named motic_x, lcm_x, motic_y, lcm_y
#     """
#     from sklearn.linear_model import LinearRegression
#     linear_regressor_x = LinearRegression() 
#     linear_regressor_y = LinearRegression() 
#     import pandas

#     motic_vs_lcm = pandas.read_csv(filename)
#     motic_x = motic_vs_lcm['x_motic'].to_numpy().reshape(-1, 1)
#     lcm_x = motic_vs_lcm['x_lcm'].to_numpy().reshape(-1, 1)
#     motic_y = motic_vs_lcm['y_motic'].to_numpy().reshape(-1, 1)
#     lcm_y = motic_vs_lcm['y_lcm'].to_numpy().reshape(-1, 1)
    
#     if direction == "lcm2motic":
#         model_x = linear_regressor_x.fit(lcm_x, motic_x)  
#         model_y = linear_regressor_y.fit(lcm_y, motic_y)  
#     else:
#         model_x = linear_regressor_x.fit(motic_x, lcm_x)  
#         model_y = linear_regressor_y.fit(motic_y, lcm_y)  
    
#     multiplier_x = model_x.coef_[0][0]
#     transform_x = model_x.intercept_[0]
#     multiplier_y = model_y.coef_[0][0]
#     transform_y = model_y.intercept_[0]
        
#     print(f"{multiplier_x:.15f}", f"{multiplier_y:.15f}", f"{transform_x:.15f}", f"{transform_y:.15f}")
#     return {'multiplier_x':multiplier_x, 'multiplier_y':multiplier_y, 'transform_x':transform_x, 'transform_y':transform_y}

# def qupath2palm(filename, multiplier_x, multiplier_y, transform_x, transform_y):
#     """ 
#     Generates palm elements text file from groJSON
#     multiplier_x, multiplier_y, transform_x, transform_y: get these calues from calculate_lm() ideally
#     """

#     import json
    
#     with open(filename) as json_file: #QuPath/rectangles_nocollection.geojson
#         qupath = json.load(json_file)
    
#     colour = "red"
#     thickness = 2
#     counter = 1
#     cutshot = "0,0"
#     multiplier_x = multiplier_x # 4.40*0.85 # 4.3956
#     multiplier_y = multiplier_y # 4.40*0.85 # 4.419247
#     intercept_x = transform_x # 118850.2975 # 127651
#     intercept_y = transform_y # 388333.7 - 40000#390258
# #     image_width = 199240
#     z = 6397
#     elements_text = []
#     for each in qupath:
#         polygon = each['geometry']['coordinates'][0]
#         comment = each['properties']['name']
#         polygon = [[(p[0]*multiplier_x)+intercept_x, (p[1]*multiplier_y)+intercept_y] for p in polygon]
#         # horizontal flip
#         # polygon = [[image_width - p[0], p[1]] for p in polygon]
#         area = abs((polygon[2][0]-polygon[0][0])*(polygon[2][1]-polygon[0][1]))
#         if len(polygon) == 5:
#             element_line = f"Rectangle\t{colour}\t{thickness}\t{counter}\t{cutshot}\t{area}\t{z}\t{comment}\n.\t{polygon[0][0]},{polygon[0][1]}\t{polygon[2][0]},{polygon[2][1]}"
#             print(element_line)
#             elements_text.append(element_line)
#         counter += 1    
#     elements_text = "\n\n".join(elements_text)

#     elements_text = f"""PALMRobo Elements\nVersion:	V 4.8.0.1\nDate, Time :	13.10.2022	12:14:59\nMICROMETER\nElements :\nType	Color	Thickness	No	CutShot	Area	Z	Comment	Coordinates\n\n{elements_text}
#     """

#     print(elements_text)
#     return elements_text