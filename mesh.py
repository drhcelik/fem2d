import os
from scipy import array, cos, sin, zeros, loadtxt
from scipy.sparse import lil_matrix
from scipy.sparse.linalg import spsolve
from material import materials

###############################################################################

class Node:

    def __init__(self,id,x,y,boundary=False,value=None):
        self.id = id
        self.x = x
        self.y = y
        self.boundary = boundary
        self.value = value

###############################################################################

class Region:

    def __init__(self,id,matName,orientation,source=0.0):
        self.id = id
        self.matName = matName
        self.orientation = orientation
        self.source = source
        self.T = array([[cos(orientation),-sin(orientation)],
                        [sin(orientation), cos(orientation)]])

    def calcTensor(self,matProp,solution=None):
        v = materials[self.matName][matProp].value(solution)
        return self.T * v * self.T.transpose()

###############################################################################

class Element:

    def __init__(self,nodes,region=None):
        self.node = nodes
        self.region = region
        n1,n2,n3 = self.node
        self.area = (n1.x*(n2.y-n3.y)+n2.x*(n3.y-n1.y)+n3.x*(n1.y-n2.y))/2
        self.b = [n2.y-n3.y,n3.y-n1.y,n1.y-n2.y];
        self.c = [n3.x-n2.x,n1.x-n3.x,n2.x-n1.x];

    def calcSourceVec(self):
        return 3*[self.region.source*self.area/3]

    def calcDiffMat(self,matProp):
        k = self.region.calcTensor(matProp)
        self.Ke = zeros((3,3))
        for j in range(3):
            coefj = array([[self.b[j]],[self.c[j]]])
            for i in range(3):
                coefi = array([self.b[i],self.c[i]])
                self.Ke[j,i] = -coefi.dot(k).dot(coefj)/(4*self.area)
        return self.Ke

###############################################################################

class Mesh:

    def __init__(self,dirname):
        self.dirname = dirname
        self.readFiles()

    def solve(self):

        NN = len(self.node)
        rhs = zeros(NN)
        K = lil_matrix((NN,NN))

        # loop through all the elements
        for e in self.element:

            # initial Ke and fe
            Ke = e.calcDiffMat('PERMEABILITY')
            Se = e.calcSourceVec()

            for i,ni in enumerate(e.node):
                rhs[ni.id] -= Se[i]
                if ni.boundary:
                    rhs[ni.id] = ni.value
                    K[ni.id,ni.id] = 1
                else:
                    for j,nj in enumerate(e.node):
                        if nj.boundary:
                            rhs[ni.id] -= Ke[i,j]*nj.value
                            K[ni.id,nj.id] = 0
                        else:
                            K[ni.id,nj.id] += Ke[i,j]

        # solve the system of linear equations and put solution on nodes
        solution = spsolve(K.tocsr(),rhs)
        for i in range(len(solution)):
            self.node[i].value = solution[i]

    def readFiles(self):

        # read nodes and the boundary values
        self.node = []
        with open(os.path.join(self.dirname,"nodes.txt")) as fnodes:
            for id,line in enumerate(fnodes.readlines()):
                x,y = line.split()
                self.node.append(Node(id,float(x),float(y)))
        vals = loadtxt(os.path.join(self.dirname,"uconsvals.txt"),unpack=True)[2]
        try:
            vals = list(vals)
        except:
            vals = [vals]
        with open(os.path.join(self.dirname,"ucons.txt")) as fboundelems:
            for line in fboundelems:
                line = line.split()
                self.node[int(line[0])-1].boundary = True
                self.node[int(line[0])-1].value = vals[int(line[2])-1]

        # read regions (materials and orientations)
        self.region = []
        with open(os.path.join(self.dirname,"orientations.txt")) as forient:
            with open(os.path.join(self.dirname,"materials.txt")) as fmaterial:
                with open(os.path.join(self.dirname,"sources.txt")) as fsources:
                    for id,(orient,matName,j) in enumerate(zip(forient,fmaterial,fsources)):
                        matName = matName.split()[0]
                        j = j.split()[0]
                        self.region.append( Region(id,matName,float(orient),float(j)) )

        # read elements
        self.element = []
        with open(os.path.join(self.dirname,"elems.txt")) as felements:
            for line in felements.readlines():
                line = line.split()
                nodes = [ self.node[int(line[i])-1] for i in range(3) ]
                region = self.region[int(line[3])-1]
                self.element.append( Element(nodes,region) )

    #----------------------------------------------------------------------

    def readSolution(self):
        with open(os.path.join(self.dirname,"solu2.txt")) as fsolution:
            for node in self.node:
                node.value = float(fsolution.readline())

    def showSolution(self):
        from mpl_toolkits.mplot3d import Axes3D
        from matplotlib import cm, pyplot
        x,y,z,tri = [],[],[],[]
        for n in self.node:
            x.append(n.x)
            y.append(n.y)
            z.append(n.value)
        for e in self.element:
            tri.append([n.id for n in e.node])
        fig = pyplot.figure()
        ax = fig.gca(projection='3d')
        ax.plot_trisurf(x, y, tri, z, cmap=cm.jet, linewidth=0.2)
        pyplot.show()

    def getVtkUnstructuredGrid(self):
        import vtk
        ugrid = vtk.vtkUnstructuredGrid()

        # insert point and point data
        points = vtk.vtkPoints()
        array  = vtk.vtkFloatArray()
        for n in self.node:
            points.InsertPoint(n.id,n.x,n.y,0.0)
            array.InsertNextValue(n.value)
        ugrid.SetPoints(points)
        ugrid.GetPointData().SetScalars(array)

        #insert cells and cell data
        for e in self.element:
            cell = vtk.vtkIdList()
            for i in [0,1,2]:
                cell.InsertNextId(e.node[i].id)
            ugrid.InsertNextCell(vtk.VTK_TRIANGLE,cell)

        return ugrid

    def writeVTKfile(self,filename):
        import vtk
        ugrid = self.getVtkUnstructuredGrid()
        writer = vtk.vtkUnstructuredGridWriter()
        if vtk.vtkVersion.GetVTKMajorVersion() <= 5:
            writer.SetInput(ugrid)
        else:
            writer.SetInputData(ugrid)
        writer.SetFileName(filename)
        writer.Write()

###############################################################################

if __name__ == "__main__":

    import sys

    try:
        mesh = Mesh(sys.argv[1])
    except:
        print "Something went wrong in your problem definition"
        exit()

    mesh.solve()
    mesh.showSolution()
    mesh.writeVTKfile("out.vtk")
