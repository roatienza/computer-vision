"""Layer utils

Utility functions for computing IOU, anchor boxes, masks,
and bounding box offsets

"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import numpy as np
import config
import math
from tensorflow.keras import backend as K

def anchor_sizes(n_layers=4):
    """Generate linear distribution of sizes depending on 
    the number of ssd top layers

    Arguments:
        n_layers (int): Number of ssd head layers

    Returns:
        sizes (list): A list of anchor sizes
    """
    s = np.linspace(0.2, 0.9, n_layers + 1)
    sizes = []
    for i in range(len(s) - 1):
        # size = [s[i], (s[i] * 0.5)]
        size = [s[i], math.sqrt(s[i] * s[i + 1])]
        sizes.append(size)

    return sizes


def anchor_boxes(feature_shape,
                 image_shape,
                 index=0,
                 n_layers=4,
                 aspect_ratios=(1, 2, 0.5)):
    """ Compute the anchor boxes per feature map
    anchor boxes are in minmax format

    Arguments:
        feature_shape (list): feature map shape
        image_shape (list): image size shape
        index (int): indicates which of ssd head n_layers
            are we referring to
        n_layers (int): Number of ssd head layers

    Returns:
        list of anchor boxes 

    """
    
    # anchor box sizes
    sizes = anchor_sizes(n_layers)[index]
    # -1 bec only 1 of the 2 sizes is used
    n_boxes = len(aspect_ratios) + len(sizes) - 1
    image_height, image_width, _ = image_shape
    # ignore number of feature maps (last)
    feature_height, feature_width, _ = feature_shape

    # normalized width and height
    # I think 0 should be index since this is normalized wrt layer num
    norm_height = image_height * sizes[0]
    norm_width = image_width * sizes[0]

    # list of anchor boxes (width, height)
    width_height = []
    # anchor box by aspect ratio on resized image dims
    # Equation 11.2.3 in Chapter 11
    for ar in aspect_ratios:
        box_height = norm_height / np.sqrt(ar)
        box_width = norm_width * np.sqrt(ar)
        width_height.append((box_width, box_height))
    # anchor box by size[1] for aspect_ratio = 1
    # Equation 11.2.4 in Chapter 11
    for size in sizes[1:]:
        box_height = image_height * size
        box_width = image_width * size
        width_height.append((box_width, box_height))

    # now an array of (width, height)
    width_height = np.array(width_height)

    # dimensions of each receptive field in pixels
    grid_width = image_width / feature_width
    grid_height = image_height / feature_height

    # compute center of receptive field per feature pt
    # (cx, cy) format 
    # starting at midpoint of 1st receptive field
    start = grid_width * 0.5 
    # ending at midpoint of last receptive field
    end = (feature_width - 0.5) * grid_width
    cx = np.linspace(start, end, feature_width)

    start = grid_height * 0.5
    end = (feature_height - 0.5) * grid_height
    cy = np.linspace(start, end, feature_height)

    # grid of box centers
    cx_grid, cy_grid = np.meshgrid(cx, cy)

    # for np.tile()
    cx_grid = np.expand_dims(cx_grid, -1) 
    cy_grid = np.expand_dims(cy_grid, -1)

    # tensor = (feature_map_height, feature_map_width, n_boxes, 4)
    # last dimension = (cx, cy, w, h)
    boxes = np.zeros((feature_height, feature_width, n_boxes, 4))
    
    # orig which may be wrong
    #boxes[..., 0] = np.tile(cy_grid, (1, 1, n_boxes))
    #boxes[..., 1] = np.tile(cx_grid, (1, 1, n_boxes))

    #should this be the correct
    boxes[..., 0] = np.tile(cx_grid, (1, 1, n_boxes))
    boxes[..., 1] = np.tile(cy_grid, (1, 1, n_boxes))

    boxes[..., 2] = width_height[:, 0]
    boxes[..., 3] = width_height[:, 1]
    # convert (cx, cy, w, h) to (xmin, xmax, ymin, ymax)
    # prepend one dimension to boxes 
    # to account for the batch size and tile it along
    # the result will be a 5D tensor of shape 
    # (batch_size, feature_map_height, feature_map_width, n_boxes, 4)
    boxes = centroid2minmax(boxes)
    boxes = np.expand_dims(boxes, axis=0)
    #boxes = np.tile(boxes, (feature_shape[0], 1, 1, 1, 1))
    #boxes = np.tile(boxes, (feature_shape[0], 1, 1, 1, 1))
    return boxes

def centroid2minmax(boxes):
    """Centroid format to minmax format 
    (cx, cy, w, h) to (xmin, xmax, ymin, ymax)
    """
    minmax= np.copy(boxes).astype(np.float)
    minmax[..., 0] = boxes[..., 0] - (0.5 * boxes[..., 2])
    minmax[..., 1] = boxes[..., 0] + (0.5 * boxes[..., 2])
    minmax[..., 2] = boxes[..., 1] - (0.5 * boxes[..., 3])
    minmax[..., 3] = boxes[..., 1] + (0.5 * boxes[..., 3])
    return minmax

# minmax to centroid format
# (xmin, xmax, ymin, ymax) to (cx, cy, w, h)
def minmax2centroid(boxes):
    centroid = np.copy(boxes).astype(np.float)
    centroid[..., 0] = 0.5 * (boxes[..., 1] - boxes[..., 0])
    centroid[..., 0] += boxes[..., 0] 
    centroid[..., 1] = 0.5 * (boxes[..., 3] - boxes[..., 2])
    centroid[..., 1] += boxes[..., 2] 
    centroid[..., 2] = boxes[..., 1] - boxes[..., 0]
    centroid[..., 3] = boxes[..., 3] - boxes[..., 2]
    return centroid

# compute intersection of boxes1 and boxes2
def intersection(boxes1, boxes2):
    m = boxes1.shape[0] # The number of boxes in `boxes1`
    n = boxes2.shape[0] # The number of boxes in `boxes2`

    xmin = 0
    xmax = 1
    ymin = 2
    ymax = 3

    boxes1_min = np.expand_dims(boxes1[:, [xmin, ymin]], axis=1)
    boxes1_min = np.tile(boxes1_min, reps=(1, n, 1))
    boxes2_min = np.expand_dims(boxes2[:, [xmin, ymin]], axis=0)
    boxes2_min = np.tile(boxes2_min, reps=(m, 1, 1))
    min_xy = np.maximum(boxes1_min, boxes2_min)

    boxes1_max = np.expand_dims(boxes1[:, [xmax, ymax]], axis=1)
    boxes1_max = np.tile(boxes1_max, reps=(1, n, 1))
    boxes2_max = np.expand_dims(boxes2[:, [xmax, ymax]], axis=0)
    boxes2_max = np.tile(boxes2_max, reps=(m, 1, 1))
    max_xy = np.minimum(boxes1_max, boxes2_max)

    side_lengths = np.maximum(0, max_xy - min_xy)

    intersection_areas = side_lengths[:, :, 0] * side_lengths[:, :, 1]
    return intersection_areas


# compute union of boxes1 and boxes2
def union(boxes1, boxes2, intersection_areas):
    m = boxes1.shape[0] # number of boxes in boxes1
    n = boxes2.shape[0] # number of boxes in boxes2

    xmin = 0
    xmax = 1
    ymin = 2
    ymax = 3

    width = (boxes1[:, xmax] - boxes1[:, xmin])
    height = (boxes1[:, ymax] - boxes1[:, ymin])
    areas = width * height
    boxes1_areas = np.tile(np.expand_dims(areas, axis=1), reps=(1,n))
    width = (boxes2[:,xmax] - boxes2[:,xmin])
    height = (boxes2[:,ymax] - boxes2[:,ymin])
    areas = width * height
    boxes2_areas = np.tile(np.expand_dims(areas, axis=0), reps=(m,1))

    union_areas = boxes1_areas + boxes2_areas - intersection_areas
    return union_areas


# compute iou of boxes1 and boxes2
def iou(boxes1, boxes2):
    intersection_areas = intersection(boxes1, boxes2)
    union_areas = union(boxes1, boxes2, intersection_areas)
    return intersection_areas / union_areas

# retrieve ground truth class, bbox offset, and mask
def get_gt_data(iou,
                n_classes=6,
                anchors=None,
                labels=None,
                normalize=False):
    # each maxiou_per_get is index of anchor w/ max iou
    # for the given ground truth bounding box
    maxiou_per_gt = np.argmax(iou, axis=0)
    
    # get the extra anchor boxes based on IoU
    threshold = config.params['gt_label_iou_thresh']
    if threshold < 1.0:
        iou_gt_thresh = np.argwhere(iou>threshold)
        if iou_gt_thresh.size > 0:
            extra_anchors = iou_gt_thresh[:,0]
            extra_classes = iou_gt_thresh[:,1]
            extra_labels = labels[:,:][extra_classes]
            indexes = [maxiou_per_gt, extra_anchors]
            maxiou_per_gt = np.concatenate(indexes,
                                           axis=0)
            labels = np.concatenate([labels, extra_labels],
                                    axis=0)

    # mask generation
    gt_mask = np.zeros((iou.shape[0], 4))
    gt_mask[maxiou_per_gt] = 1.0

    # class generation
    gt_class = np.zeros((iou.shape[0], n_classes))
    # by default all are background
    gt_class[:, 0] = 1
    # but those that belong to maxiou_per_gt are not
    gt_class[maxiou_per_gt, 0] = 0
    # we have to find those column indeces (classes)
    maxiou_col = np.reshape(maxiou_per_gt, (maxiou_per_gt.shape[0], 1))
    label_col = np.reshape(labels[:,4], (labels.shape[0], 1)).astype(int)
    row_col = np.append(maxiou_col, label_col, axis=1)
    # the label of object in maxio_per_gt
    gt_class[row_col[:,0], row_col[:,1]]  = 1.0
    
    # offset generation
    gt_offset = np.zeros((iou.shape[0], 4))
    anchors = np.reshape(anchors, [-1, 4])

    #(cx, cy, w, h) format
    if normalize:
        anchors = minmax2centroid(anchors)
        labels = minmax2centroid(labels)
        # ((cx_gt - cx_anchor) / w_anchor) / 0.1
        # ((cy_gt - cy_anchor) / h_anchor) / 0.1
        offsets1 = labels[:, 0:2] - anchors[maxiou_per_gt, 0:2]
        offsets1 /= anchors[maxiou_per_gt, 2:4]
        offsets1 /= 0.1

        # log(w_gt / w_anchor) / 0.2
        # log(h_gt / h_anchor) / 0.2
        offsets2 = np.log(labels[:, 2:4] / anchors[maxiou_per_gt, 2:4])
        offsets2 /= 0.2  

        offsets = np.concatenate([offsets1, offsets2], axis=-1)

    # (xmin, xmax, ymin, ymax) format
    else:
        offsets = labels[:, 0:4] - anchors[maxiou_per_gt]

    gt_offset[maxiou_per_gt] = offsets

    return gt_class, gt_offset, gt_mask
